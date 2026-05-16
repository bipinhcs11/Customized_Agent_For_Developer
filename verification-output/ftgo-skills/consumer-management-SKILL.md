---
skill: Consumer Management
domain: consumer-management
version: 1
project_type: REST API
framework: Spring Boot
java_version: 8
legacy: false
status: active
flags: shared
related_skills: accounting-authorization
generated_by: skill_generator.agent
last_updated: 2026-05-15
---

# Consumer Management

## Purpose
Registers new consumers, looks them up by id, and authorizes whether a given consumer is permitted to place an order of a given total. Acts as the authoritative source of consumer identity for the food-to-go platform and as a participant in the create-order workflow so other parts of the platform do not have to re-implement consumer eligibility checks.

## Entry Points
- REST:  POST /consumers -> ConsumerController.create()
- REST:  GET /consumers/{consumerId} -> ConsumerController.get()
- Event: Saga command on channel "consumerService" (ValidateOrderByConsumer) -> ConsumerServiceCommandHandlers.validateOrderForConsumer()

## Business Logic

### Core Flow
1. HTTP POST /consumers is received and deserialized into a CreateConsumerRequest carrying a PersonName -- ConsumerController.create()
2. The controller delegates creation to the service layer, which builds a Consumer aggregate together with its domain events -- ConsumerService.create()
3. The new Consumer is persisted via the Spring Data repository -- ConsumerService.create()
4. Domain events produced by the aggregate factory are published through the Tram DomainEventPublisher under the Consumer aggregate type and id -- ConsumerService.create()
5. The controller wraps the new consumer id in a CreateConsumerResponse and returns it to the caller -- ConsumerController.create()
6. HTTP GET /consumers/{consumerId} looks the consumer up and, if found, returns a GetConsumerResponse with the consumer name; otherwise it returns HTTP 404 -- ConsumerController.get()
7. A ValidateOrderByConsumer saga command arriving on the "consumerService" channel is dispatched to the command handler -- ConsumerServiceCommandHandlers.commandHandlers()
8. The handler asks the service to validate the order for the consumer; on success it replies with withSuccess(), on ConsumerVerificationFailedException it replies with withFailure() -- ConsumerServiceCommandHandlers.validateOrderForConsumer()
9. The service loads the Consumer by id and, if absent, throws ConsumerNotFoundException; otherwise it delegates the eligibility check to the aggregate's validateOrderByConsumer(orderTotal) -- ConsumerService.validateOrderForConsumer()

### Validation Rules
- POST /consumers requires a JSON body that deserializes into CreateConsumerRequest with a non-null PersonName (inferred from CreateConsumerRequest constructor and ConsumerController.create()) -- ConsumerController.create()
- GET /consumers/{consumerId} requires a numeric path variable bound to a long -- ConsumerController.get()
- A ValidateOrderByConsumer command must carry consumerId, orderId, and an orderTotal Money value (inferred from ValidateOrderByConsumer constructor and ValidateOrderByConsumerTest.shouldDeserialize()) -- ValidateOrderByConsumer.ValidateOrderByConsumer()
- The consumer referenced by an incoming saga command must exist in the repository; if not, ConsumerNotFoundException is thrown -- ConsumerService.validateOrderForConsumer()
- The Consumer aggregate enforces the actual order-eligibility rule against the order total (inferred from ConsumerService.validateOrderForConsumer() calling Consumer.validateOrderByConsumer(orderTotal)) -- Consumer.validateOrderByConsumer()

### Business Rules
- Creating a consumer is an atomic, transactional act: the consumer is persisted and its domain events are published in the same transaction -- ConsumerService.create()
- The Consumer aggregate is the only place that decides whether a given order total is acceptable for the consumer; the service merely loads and dispatches (inferred from ConsumerService.validateOrderForConsumer()) -- Consumer.validateOrderByConsumer()
- A missing consumer in an order-validation saga step is a verification failure, not a system error, and is converted into a saga failure reply -- ConsumerServiceCommandHandlers.validateOrderForConsumer()
- All consumer-related saga traffic flows over a single logical channel named "consumerService" -- ConsumerServiceChannels.consumerServiceChannel
- The lookup endpoint exposes only the consumer's name, never internal aggregate state (inferred from GetConsumerResponse fields) -- ConsumerController.get()

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| ConsumerServiceMain.java | Config | Spring Boot entry point importing ConsumerWebConfiguration, TramJdbcKafkaConfiguration, CommonSwaggerConfiguration |
| ConsumerWebConfiguration.java | Config | Web-tier @Configuration with @ComponentScan that imports ConsumerServiceConfiguration |
| ConsumerServiceConfiguration.java | Config | Domain-tier @Configuration enabling JPA repositories, transactions, Tram events publisher and Saga participant; declares ConsumerService, ConsumerServiceCommandHandlers, and saga CommandDispatcher beans |
| ConsumerController.java | Controller | REST endpoints for creating and fetching consumers under /consumers |
| CreateConsumerRequest.java | DTO | Inbound payload carrying a PersonName for POST /consumers |
| CreateConsumerResponse.java | DTO | Outbound payload exposing the new consumerId |
| GetConsumerResponse.java | DTO | Outbound payload exposing the consumer's PersonName for GET /consumers/{id} |
| ConsumerService.java | Service | Application service: create(), findById(), and validateOrderForConsumer() |
| ConsumerRepository.java | Repository | Spring Data CrudRepository<Consumer, Long> for consumer persistence |
| ConsumerServiceCommandHandlers.java | Service | Saga command handler binding ValidateOrderByConsumer on the "consumerService" channel to the service |
| ConsumerCreated.java | Event | Tram DomainEvent published when a consumer is created (one copy in consumer-service, one in accounting-service for cross-service consumption) |
| ConsumerNotFoundException.java | Exception | Thrown when an order-validation saga command references an unknown consumerId; subclass of ConsumerVerificationFailedException |
| ConsumerVerificationFailedException.java | Exception | Base RuntimeException for any consumer-side verification failure of an order |
| ConsumerServiceChannels.java | Constant | Holds the "consumerService" channel name used by saga messaging |
| ValidateOrderByConsumer.java | Command DTO | Tram saga Command carrying consumerId, orderId, orderTotal |
| ConsumerControllerTest.java | Test | Standalone MockMvc test for GET /consumers/{id} including OpenAPI request/response validation against ftgo-consumer-service-swagger.json |
| ConsumerServiceInMemoryIntegrationTest.java | Test | In-memory Tram integration test exercising POST /consumers and the ValidateOrderByConsumer saga reply on the "consumerService" channel |
| ValidateOrderByConsumerTest.java | Test | JSON-schema deserialization test for the ValidateOrderByConsumer command using /ValidateOrderByConsumer.json |
| ftgo-consumer-service-swagger.json | Config | Classpath OpenAPI specification used for request/response validation in ConsumerControllerTest |
| /ValidateOrderByConsumer.json | Config | Classpath JSON schema used to validate the ValidateOrderByConsumer command shape |

## Data Flow
HTTP POST /consumers
  -> ConsumerController.create()
  -> ConsumerService.create()
  -> Consumer.create() (aggregate factory producing ResultWithEvents<Consumer>)
  -> ConsumerRepository.save()
  -> DomainEventPublisher.publish() (Consumer aggregate, ConsumerCreated event)
  -> CreateConsumerResponse JSON to client

HTTP GET /consumers/{consumerId}
  -> ConsumerController.get()
  -> ConsumerService.findById()
  -> ConsumerRepository.findById()
  -> GetConsumerResponse JSON or HTTP 404

Saga command on "consumerService" channel (ValidateOrderByConsumer)
  -> ConsumerServiceCommandHandlers.commandHandlers() (SagaCommandHandlersBuilder)
  -> ConsumerServiceCommandHandlers.validateOrderForConsumer()
  -> ConsumerService.validateOrderForConsumer()
  -> ConsumerRepository.findById()
  -> Consumer.validateOrderByConsumer(orderTotal)
  -> withSuccess() or withFailure() reply message back to the saga orchestrator

## Database & Storage
- Tables: consumer aggregate table managed by Spring Data JPA via ConsumerRepository (Consumer @Entity; exact table name not present in supplied sources -- inferred from ConsumerRepository extending CrudRepository<Consumer, Long>)
- Stored procs: none found
- File paths: classpath resource ftgo-consumer-service-swagger.json (ConsumerControllerTest.configureControllers()); classpath resource /ValidateOrderByConsumer.json (ValidateOrderByConsumerTest.shouldDeserialize())
- Queues: logical Tram channel "consumerService" (ConsumerServiceChannels.consumerServiceChannel) used for saga command messages; physical transport is Kafka via TramJdbcKafkaConfiguration imported by ConsumerServiceMain
- Cache keys: none found

## External Dependencies
- io.eventuate.tram.events.publisher.DomainEventPublisher -- publishes ConsumerCreated and any other Consumer aggregate events emitted by Consumer.create() -- ConsumerService.create()
- io.eventuate.tram.sagas.participant.SagaCommandHandlersBuilder / SagaCommandDispatcherFactory -- builds the saga participant command dispatcher bound to the "consumerService" channel -- ConsumerServiceCommandHandlers.commandHandlers(), ConsumerServiceConfiguration.commandDispatcher()
- io.eventuate.tram.spring.jdbckafka.TramJdbcKafkaConfiguration -- provides the Kafka + JDBC transport for Tram messaging -- ConsumerServiceMain
- net.chrisrichardson.eventstore.examples.customersandorders.commonswagger.CommonSwaggerConfiguration -- supplies Swagger UI for the REST API -- ConsumerServiceMain
- net.chrisrichardson.ftgo.common.CommonConfiguration -- imported to provide shared platform beans -- ConsumerServiceConfiguration
- net.chrisrichardson.ftgo.common.Money -- value object used for orderTotal in ValidateOrderByConsumer and Consumer.validateOrderByConsumer() -- ValidateOrderByConsumer, ConsumerService.validateOrderForConsumer()
- net.chrisrichardson.ftgo.common.PersonName -- value object carried by CreateConsumerRequest and GetConsumerResponse -- ConsumerController.create(), ConsumerController.get()
- Order-side saga orchestrator (the create-order saga in ftgo-order-service) -- sends ValidateOrderByConsumer commands to this service over the "consumerService" channel (inferred from ConsumerServiceCommandHandlers.commandHandlers())

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| ConsumerNotFoundException | ConsumerRepository.findById() returns empty during saga validation | Thrown from ConsumerService.validateOrderForConsumer(); caught in ConsumerServiceCommandHandlers.validateOrderForConsumer() and converted to withFailure() saga reply |
| ConsumerVerificationFailedException | Any consumer-side eligibility failure (superclass of ConsumerNotFoundException, also thrown from Consumer.validateOrderByConsumer() when business rules reject the order) | Caught in ConsumerServiceCommandHandlers.validateOrderForConsumer() and converted to withFailure() saga reply |
| ResponseEntity HttpStatus.NOT_FOUND | ConsumerService.findById() returns Optional.empty() | Returned as ResponseEntity with HttpStatus.NOT_FOUND from ConsumerController.get() |

## Edge Cases
- Missing consumer on lookup -- ConsumerController.get() returns HTTP 404 via Optional.map/.orElseGet() rather than throwing -- ConsumerController.get()
- Missing consumer during saga validation is mapped to a saga failure reply, not a 5xx -- ConsumerServiceCommandHandlers.validateOrderForConsumer()
- Consumer creation persistence and event publication are wrapped in @Transactional so a publish or save failure rolls back the new consumer -- ConsumerService.create()
- ValidateOrderByConsumer has a private no-arg constructor to support framework deserialization while still requiring the three-arg constructor in code -- ValidateOrderByConsumer.ValidateOrderByConsumer()
- CreateConsumerRequest has a private no-arg constructor to support Jackson deserialization without exposing a default-constructed DTO to callers -- CreateConsumerRequest.CreateConsumerRequest()
- GetConsumerResponse extends CreateConsumerResponse, so the GET payload also includes the inherited consumerId field even though the constructor only sets name (inferred from GetConsumerResponse.GetConsumerResponse()) -- GetConsumerResponse.GetConsumerResponse()
- Equality, hashCode, and toString on ValidateOrderByConsumer use reflection-based builders, so adding a field automatically participates in equality and logging -- ValidateOrderByConsumer.equals(), ValidateOrderByConsumer.hashCode(), ValidateOrderByConsumer.toString()
- A second copy of ConsumerCreated lives under ftgo-accounting-service in the same package, allowing the accounting service to consume the event without depending on the consumer service module -- ConsumerCreated (ftgo-accounting-service copy)

## Legacy Notes
none found

## Related Skills
| Domain | Relationship | Reason |
|--------|-------------|--------|
| accounting-authorization | calls | ConsumerService.create() publishes ConsumerCreated event which triggers AccountService.create() to provision the consumer's account in the accounting-authorization domain. |

## AI Agent Instructions
1. Before changing how a consumer is created, re-read ConsumerService.create() and confirm that any new step still runs inside the @Transactional boundary and still publishes events through DomainEventPublisher.publish() so the create + publish atomicity is preserved.
2. Never change the saga reply contract in ConsumerServiceCommandHandlers.validateOrderForConsumer(): success must remain withSuccess() and any ConsumerVerificationFailedException (including ConsumerNotFoundException) must remain withFailure(), otherwise the create-order saga in ftgo-order-service will hang or compensate incorrectly.
3. Any new consumer-side eligibility rule must be added inside the Consumer aggregate's validateOrderByConsumer(orderTotal) method, not in ConsumerService or the controller, so that the saga path and any future direct callers share the same rule.
4. Do not rename or change the literal "consumerService" string in ConsumerServiceChannels.consumerServiceChannel; it is the contract between this service and every saga that targets it -- update ConsumerServiceCommandHandlers.commandHandlers() and the order-side proxy together if it ever has to change.
5. Run the in-memory end-to-end check via ConsumerServiceInMemoryIntegrationTest (POST /consumers + ValidateOrderByConsumer reply on "consumerService") and the controller-layer OpenAPI check via ConsumerControllerTest before declaring a change safe; both rely on ftgo-consumer-service-swagger.json staying in sync with ConsumerController.
6. If you add a new field to ValidateOrderByConsumer, update /ValidateOrderByConsumer.json (validated by ValidateOrderByConsumerTest.shouldDeserialize()) and remember that ValidateOrderByConsumer.equals()/hashCode()/toString() are reflection-based and will pick up the new field automatically.
7. Treat both copies of ConsumerCreated (ftgo-consumer-service and ftgo-accounting-service) as a shared wire contract; any field change must be made in both and coordinated with consumers of the event.
