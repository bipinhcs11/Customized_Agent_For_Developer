---
skill: Consumer Management
domain: consumer-management
version: 1
project_type: REST API
framework: Spring Boot
java_version: 8
legacy: false
status: active
flags: none
related_skills: PLACEHOLDER
generated_by: skill_generator.agent
last_updated: 2026-05-15
---

# Consumer Management

## Purpose
Registers customers who place food orders, exposes their basic identity for lookup, and authorizes whether a given customer is allowed to spend a given amount on an order. This authorization step is the gate the order workflow consults before a new order is allowed to proceed.

## Entry Points
- REST:  POST /consumers              -> ConsumerController.create()
- REST:  GET  /consumers/{consumerId} -> ConsumerController.get()
- Event: Command channel "consumerService" carrying ValidateOrderByConsumer -> ConsumerServiceCommandHandlers.validateOrderForConsumer()

## Business Logic

### Core Flow
1. A new consumer is registered from a name payload and persisted, then a creation event is published to the domain event stream — ConsumerService.create().
2. An existing consumer can be looked up by id and their name returned, or a 404 is produced when absent — ConsumerController.get().
3. A saga command arriving on the "consumerService" channel triggers an order-authorization check for a given consumerId and orderTotal — ConsumerServiceCommandHandlers.validateOrderForConsumer().
4. The authorization loads the consumer by id and delegates the spend check to the aggregate; missing consumers raise a not-found exception — ConsumerService.validateOrderForConsumer().
5. On success a saga success reply is emitted; on a verification failure a saga failure reply is emitted — ConsumerServiceCommandHandlers.validateOrderForConsumer().

### Validation Rules
- Consumer must exist for the supplied consumerId or the validation fails with ConsumerNotFoundException — ConsumerService.validateOrderForConsumer().
- Order-by-consumer spend rule is delegated to Consumer.validateOrderByConsumer() (inferred from ConsumerService.validateOrderForConsumer()).

### Business Rules
- Creating a consumer is transactional and atomically persists the aggregate and publishes its creation events — ConsumerService.create().
- ConsumerNotFoundException is a subtype of ConsumerVerificationFailedException, so a missing consumer is treated as a verification failure by the saga handler — ConsumerNotFoundException, ConsumerServiceCommandHandlers.validateOrderForConsumer().
- Verification failures are converted to a saga withFailure() reply rather than propagated as exceptions — ConsumerServiceCommandHandlers.validateOrderForConsumer().

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| ConsumerServiceMain.java | Config | Spring Boot entry point; imports web, Tram JDBC/Kafka, Swagger configs |
| ConsumerController.java | Controller | REST endpoints for create and get consumer |
| CreateConsumerRequest.java | DTO | Request body for POST /consumers |
| CreateConsumerResponse.java | DTO | Response carrying the new consumerId |
| GetConsumerResponse.java | DTO | Response carrying the consumer's PersonName |
| ConsumerWebConfiguration.java | Config | Web-tier @ComponentScan and import of ConsumerServiceConfiguration |
| ConsumerServiceConfiguration.java | Config | JPA, saga participant, Tram event publisher wiring; declares ConsumerService, ConsumerServiceCommandHandlers, CommandDispatcher beans |
| ConsumerService.java | Service | Application service for create / findById / validateOrderForConsumer |
| ConsumerRepository.java | Repository | Spring Data CrudRepository<Consumer, Long> |
| ConsumerServiceCommandHandlers.java | Service | Saga command handler bound to channel "consumerService" |
| ConsumerCreated.java | Event | DomainEvent emitted on consumer creation |
| ValidateOrderByConsumer.java | Command | Saga command (consumerId, orderId, orderTotal) |
| ConsumerVerificationFailedException.java | Exception | Base verification failure type |
| ConsumerNotFoundException.java | Exception | Specialization signalling consumer lookup miss |
| ConsumerServiceChannels.java | Constant | Defines the "consumerService" command channel name |

## Data Flow
```
POST /consumers
   |
   v
ConsumerController.create(CreateConsumerRequest)
   |   request.getName() -> PersonName
   v
ConsumerService.create(name)                        @Transactional
   |
   |-- Consumer.create(name)                         <- builds aggregate + ConsumerCreated event list
   |
   |-- consumerRepository.save(rwe.result)           -> Consumer DB (JPA, MySQL)
   |
   |__ domainEventPublisher.publish(Consumer.class, id, rwe.events)
              -> Eventuate Tram outbox -> Kafka topic net.chrisrichardson.ftgo.consumerservice.domain.Consumer
              + emit ConsumerCreated domain event

GET /consumers/{consumerId}
   |
   v
ConsumerController.get(consumerId)
   |
   |__ ConsumerService.findById(consumerId)
              consumerRepository.findById(consumerId) -> Consumer DB
              |
              |-- present  -> 200 OK + GetConsumerResponse(consumer.getName())
              |__ absent   -> 404 NOT_FOUND          <- orElseGet fallback

@KafkaListener (Tram saga dispatch on channel "consumerService")
   |
   v
CommandDispatcher (consumerServiceDispatcher)
   |   built by SagaCommandDispatcherFactory.make(...)
   v
ConsumerServiceCommandHandlers.commandHandlers()
   |   SagaCommandHandlersBuilder.fromChannel("consumerService")
   |
   |-- onMessage(ValidateOrderByConsumer.class)
           |
           v
       ConsumerServiceCommandHandlers.validateOrderForConsumer(cm)
           |   cm.getCommand() -> (consumerId, orderId, orderTotal)
           |
           |-- ConsumerService.validateOrderForConsumer(consumerId, orderTotal)
           |       |
           |       |-- consumerRepository.findById(consumerId)   -> Consumer DB
           |       |       |__ empty -> throw ConsumerNotFoundException   <- orElseThrow guard
           |       |
           |       |__ Consumer.validateOrderByConsumer(orderTotal)
           |               <- spend rule on the aggregate; throws ConsumerVerificationFailedException on breach
           |
           |-- success path -> withSuccess()                     <- saga reply on command reply channel
           |__ catch ConsumerVerificationFailedException -> withFailure()
                       <- reply only; exception is NOT propagated to Kafka
                       + saga reply published via Tram -> Kafka command-reply channel
```

## Database & Storage
- Tables: `consumer` (managed by Spring Data JPA via ConsumerRepository extends CrudRepository<Consumer, Long>); Eventuate Tram event/outbox tables provided by TramJdbcKafkaConfiguration (inferred from ConsumerServiceMain).
- Stored procs: none found
- File paths: none found
- Queues: command channel `consumerService` (ConsumerServiceChannels.consumerServiceChannel); domain event topic for aggregate `Consumer` published by DomainEventPublisher in ConsumerService.create().
- Cache keys: none found

## External Dependencies
- Eventuate Tram CommandDispatcher / SagaCommandDispatcherFactory — dispatches saga commands from Kafka to ConsumerServiceCommandHandlers (ConsumerServiceConfiguration.commandDispatcher()).
- Eventuate Tram DomainEventPublisher — publishes ConsumerCreated to Kafka via the transactional outbox (ConsumerService.create()).
- TramJdbcKafkaConfiguration — JDBC + Kafka transport wiring imported by ConsumerServiceMain.
- CommonSwaggerConfiguration — Swagger UI exposure (ConsumerServiceMain).
- Spring Data JPA / underlying RDBMS — persistence for the Consumer aggregate (ConsumerRepository).

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| ConsumerNotFoundException | consumerRepository.findById() returns empty in ConsumerService.validateOrderForConsumer() | Thrown via orElseThrow; caught upstream by ConsumerServiceCommandHandlers.validateOrderForConsumer() as ConsumerVerificationFailedException and converted to withFailure() reply |
| ConsumerVerificationFailedException | Aggregate spend rule failure in Consumer.validateOrderByConsumer() (inferred) | Caught in ConsumerServiceCommandHandlers.validateOrderForConsumer() and converted to withFailure() saga reply |

## Edge Cases
- Missing consumer on GET returns 404 via Optional.map / orElseGet fallback rather than throwing — ConsumerController.get().
- Missing consumer on saga validation is converted to a saga failure reply, not an HTTP 5xx, because ConsumerNotFoundException extends ConsumerVerificationFailedException — ConsumerServiceCommandHandlers.validateOrderForConsumer().
- create() is the only @Transactional path; validateOrderForConsumer() runs without an explicit transaction annotation (inferred from ConsumerService).

## Legacy Notes
none found

## Related Skills
| Domain | Relationship | Reason |
|--------|-------------|--------|
| PLACEHOLDER | PLACEHOLDER | PLACEHOLDER |

## AI Agent Instructions
1. Before changing any spend or authorization rule, read Consumer.validateOrderByConsumer() — the aggregate owns the rule, not ConsumerService.
2. Never let ConsumerServiceCommandHandlers.validateOrderForConsumer() propagate exceptions; it must always return withSuccess() or withFailure() so the saga reply channel stays well-formed.
3. Any new command added to channel "consumerService" must be registered in ConsumerServiceCommandHandlers.commandHandlers() and dispatched through the bean built by ConsumerServiceConfiguration.commandDispatcher(); changes here affect every saga that calls consumer-service (notably order-creation).
4. Run ConsumerServiceInMemoryIntegrationTest and ConsumerControllerTest before merging; both exercise the REST surface and the saga reply path.
5. Keep ConsumerService.create() @Transactional so the JPA save and the Tram outbox write commit together — splitting them will break exactly-once domain-event publication.
