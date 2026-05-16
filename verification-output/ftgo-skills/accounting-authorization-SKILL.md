---
skill: Accounting And Authorization
domain: accounting-authorization
version: 1
project_type: Monolith Module
framework: Spring Boot
java_version: 8
legacy: false
status: active
flags: shared
related_skills: consumer-management
generated_by: skill_generator.agent
last_updated: 2026-05-15
---

# Accounting and Authorization

## Purpose
Authorizes, reverses, and revises payment amounts against a consumer's account so an order workflow can confirm, cancel, or amend a purchase. The account is provisioned automatically when a consumer signs up, and a disabled account causes any charge attempt to fail gracefully so the order process can compensate without taking money.

## Entry Points
- Event:   forAggregateType("net.chrisrichardson.ftgo.consumerservice.domain.Consumer") onEvent(ConsumerCreated) -> AccountingEventConsumer.createAccount()
- Command: channel "accountingService" onMessage(AuthorizeCommand) -> AccountingServiceCommandHandler.authorize()
- Command: channel "accountingService" onMessage(ReverseAuthorizationCommand) -> AccountingServiceCommandHandler.reverseAuthorization()
- Command: channel "accountingService" onMessage(ReviseAuthorization) -> AccountingServiceCommandHandler.reviseAuthorization()
- REST:    GET /accounts/{accountId} -> AccountsController.getAccount()

## Business Logic

### Core Flow
1. A new consumer publishes a ConsumerCreated domain event and the accounting service subscribes to it on the Consumer aggregate channel — AccountingEventConsumer.domainEventHandlers()
2. The consumer event is handed off to the service layer to provision an account whose aggregate id equals the consumer's id — AccountingEventConsumer.createAccount()
3. The service saves a new Account aggregate by issuing a CreateAccountCommand with the consumer id pinned as the aggregate id — AccountingService.create()
4. The Account aggregate emits an AccountCreatedEvent on creation, recording that an account now exists — Account.process(CreateAccountCommand)
5. When an order saga sends an AuthorizeCommand on the accountingService channel, the command handler translates the external command into an internal command and updates the account aggregate, replying to the originating saga — AccountingServiceCommandHandler.authorize()
6. The account aggregate processes the internal authorize command and emits an AccountAuthorizedEvent to signal a successful authorization — Account.process(AuthorizeCommandInternal)
7. If the order saga compensates, a ReverseAuthorizationCommand triggers the same update path against the aggregate, producing no further events — AccountingServiceCommandHandler.reverseAuthorization() and Account.process(ReverseAuthorizationCommandInternal)
8. If the order is revised, a ReviseAuthorization command updates the aggregate with a ReviseAuthorizationCommandInternal and produces no further events — AccountingServiceCommandHandler.reviseAuthorization() and Account.process(ReviseAuthorizationCommandInternal)
9. Any of the three command handlers catch AccountDisabledException raised by the aggregate and reply with an AccountDisabledReply failure to the saga — AccountingServiceCommandHandler.authorize()
10. A REST client can fetch a known account id and receive a 200 response with that id echoed back — AccountsController.getAccount()

### Validation Rules
- none found

### Business Rules
- One account is created per consumer, identified by the consumer's id used as the aggregate id — AccountingService.create()
- Authorize, reverse, and revise commands are all dispatched on the single "accountingService" channel and routed by command type — AccountingServiceCommandHandler.commandHandlers()
- A disabled account must reply with AccountDisabledReply on any of authorize, reverse, or revise so the saga can compensate — AccountingServiceCommandHandler.authorize(), AccountingServiceCommandHandler.reverseAuthorization(), AccountingServiceCommandHandler.reviseAuthorization()
- Only the authorize command emits a domain event (AccountAuthorizedEvent); reverse and revise are intentionally event-less state transitions — Account.process(AuthorizeCommandInternal), Account.process(ReverseAuthorizationCommandInternal), Account.process(ReviseAuthorizationCommandInternal)
- External API command identifiers (consumerId as long, orderId as Long) are converted to strings before the internal aggregate command is built — AccountingServiceCommandHandler.makeAuthorizeCommandInternal(), AccountingServiceCommandHandler.makeReverseAuthorizeCommandInternal(), AccountingServiceCommandHandler.makeReviseAuthorizeCommandInternal()
- The accounting service participates in sagas via a SagaReplyRequestedEvent subscriber scoped to the Account aggregate type — AccountingMessagingConfiguration.sagaReplyRequestedEventSubscriber()
- The aggregate explicitly defines an empty apply for SagaReplyRequestedEvent because the framework requires it (inferred from Account.apply(SagaReplyRequestedEvent) TODO comment) — Account.apply(SagaReplyRequestedEvent)

## Key Classes & Files
| File | Type | Role |
|------|------|------|
| AccountsController.java | Controller | REST endpoint returning a GetAccountResponse for an account id |
| GetAccountResponse.java | DTO | Response payload carrying the account id |
| AccountingService.java (accountingservice.domain) | Service | Creates a new Account aggregate keyed by consumer id |
| Account.java | Aggregate | Event-sourced aggregate handling create, authorize, reverse, and revise commands |
| AccountCommand.java | Interface | Marker interface tying all internal commands to the Account aggregate |
| CreateAccountCommand.java | Command | Internal command that provisions a new account |
| AuthorizeCommandInternal.java | Command | Internal aggregate command for authorize, carrying string ids and Money |
| ReverseAuthorizationCommandInternal.java | Command | Internal aggregate command for reverse, carrying string ids and Money |
| ReviseAuthorizationCommandInternal.java | Command | Internal aggregate command for revise, carrying string ids and Money |
| AccountCreatedEvent.java | Event | Emitted when an account is created |
| AccountAuthorizedEvent.java | Event | Emitted on successful authorization |
| AccountAuthorizationFailed.java | Event | Authorization failure event (declared but not emitted by the aggregate methods shown) |
| AccountDisabledException.java | Exception | Thrown by the aggregate to signal a disabled account |
| AccountServiceConfiguration.java | Config | Wires the AggregateRepository<Account, AccountCommand> and AccountingService bean |
| AccountingServiceCommandHandler.java | Service | Maps external saga commands to internal aggregate commands and replies |
| AccountingEventConsumer.java | Service | Subscribes to ConsumerCreated and triggers account creation |
| AccountServiceChannelConfiguration.java | Config | Holds the command dispatcher id and channel name for the accounting service |
| AccountingMessagingConfiguration.java | Config | Wires command dispatcher, domain event dispatcher, and saga reply subscriber |
| AccountingWebConfiguration.java | Config | Imports AccountServiceConfiguration and enables component scanning for the web layer |
| AccountingServiceMain.java | Config | Spring Boot main class importing messaging, web, command, driver, and swagger configs |
| AccountingServiceChannels.java | Constants | Defines the public accountingService channel name |
| AuthorizeCommand.java | Command (API) | Public saga command requesting an authorization |
| ReverseAuthorizationCommand.java | Command (API) | Public saga command requesting an authorization reversal |
| ReviseAuthorization.java | Command (API) | Public saga command requesting an authorization revision |
| AccountDisabledReply.java | DTO (API) | Failure reply returned when the account is disabled |
| ConsumerCreated.java (consumerservice.domain, duplicated in accounting jar) | Event | External domain event signalling a new consumer to subscribe to |
| AccountingServiceCommandHandlerTest.java | Test | Spring Boot test publishing ConsumerCreated then sending AuthorizeCommand and asserting a reply |

## Data Flow
[ConsumerCreated domain event on Consumer aggregate channel]
  -> AccountingEventConsumer.createAccount()
  -> AccountingService.create()
  -> AggregateRepository<Account, AccountCommand>.save(CreateAccountCommand, withId(consumerId))
  -> Account.process(CreateAccountCommand) emits AccountCreatedEvent

[Saga sends AuthorizeCommand / ReverseAuthorizationCommand / ReviseAuthorization on "accountingService" channel]
  -> AccountingServiceCommandHandler.authorize() / reverseAuthorization() / reviseAuthorization()
  -> AggregateRepository.update(consumerId, *CommandInternal, replyingTo(cm).catching(AccountDisabledException -> withFailure(AccountDisabledReply)))
  -> Account.process(*Internal) emits AccountAuthorizedEvent (authorize) or no event (reverse/revise)
  -> Saga reply produced via SagaReplyRequestedEventSubscriber

[HTTP GET /accounts/{accountId}]
  -> AccountsController.getAccount()
  -> GetAccountResponse (HTTP 200) or HTTP 404 on EntityNotFoundException

## Database & Storage
- Tables:        Eventuate event store tables (managed by EventuateAggregateStore, no explicit @Entity in this domain)
- Stored procs:  none found
- File paths:    none found
- Queues:        Kafka via Tram JDBC-Kafka transport (TramJdbcKafkaConfiguration imported by AccountingServiceMain); public command channel "accountingService" (AccountingServiceChannels.accountingServiceChannel); internal command dispatcher id "accountCommandDispatcher" and channel "accountCommandChannel" (AccountingMessagingConfiguration.accountServiceChannelConfiguration()); domain event dispatcher id "accountingServiceDomainEventDispatcher"; saga reply subscriber id "accountingServiceSagaReplyRequestedEventSubscriber"
- Cache keys:    none found

## External Dependencies
- io.eventuate.sync.AggregateRepository<Account, AccountCommand> — saves and updates the event-sourced Account aggregate
- io.eventuate.sync.EventuateAggregateStore — backing event store used by the aggregate repository (AccountServiceConfiguration.accountRepositorySync())
- io.eventuate.tram.commands.consumer.CommandDispatcher — dispatches inbound saga commands to AccountingServiceCommandHandler (AccountingMessagingConfiguration.commandDispatcher())
- io.eventuate.tram.events.subscriber.DomainEventDispatcher — dispatches inbound ConsumerCreated events to AccountingEventConsumer (AccountingMessagingConfiguration.domainEventDispatcher())
- io.eventuate.tram.sagas.eventsourcingsupport.SagaReplyRequestedEventSubscriber — produces saga replies for the Account aggregate (AccountingMessagingConfiguration.sagaReplyRequestedEventSubscriber())
- Consumer service (upstream) — publishes ConsumerCreated on aggregate type "net.chrisrichardson.ftgo.consumerservice.domain.Consumer"
- Order saga (upstream) — publishes AuthorizeCommand, ReverseAuthorizationCommand, ReviseAuthorization on the "accountingService" channel
- API Gateway AccountingService proxy (ftgo-api-gateway) — declares findBillByOrderId but currently returns Mono.error(UnsupportedOperationException) (apiagateway.proxies.AccountingService.findBillByOrderId)
- CommonSwaggerConfiguration — exposes Swagger UI for the running service (AccountingServiceMain)

## Error Handling
| Exception | Trigger | Handling |
|-----------|---------|---------|
| AccountDisabledException | Raised when the Account aggregate refuses a command because the account is disabled (inferred from AccountingServiceCommandHandler.authorize() catching clause; the aggregate methods shown do not throw it explicitly) | Caught by the replyingTo(...).catching(...) builder in AccountingServiceCommandHandler.authorize(), reverseAuthorization(), and reviseAuthorization(); converted into withFailure(new AccountDisabledReply()) and sent back to the saga |
| EntityNotFoundException | Thrown by Eventuate when an aggregate id is not found | Caught in AccountsController.getAccount() and converted to ResponseEntity with HttpStatus.NOT_FOUND |

## Edge Cases
- The aggregate handler for SagaReplyRequestedEvent is intentionally empty with a TODO indicating the framework requires the method to exist — Account.apply(SagaReplyRequestedEvent)
- ReverseAuthorizationCommandInternal and ReviseAuthorizationCommandInternal produce Collections.emptyList(), meaning no event is emitted for reverse or revise paths — Account.process(ReverseAuthorizationCommandInternal), Account.process(ReviseAuthorizationCommandInternal)
- AccountsController.getAccount() returns the supplied accountId in a GetAccountResponse without consulting the aggregateRepository, but still declares a catch for EntityNotFoundException (inferred from AccountsController.getAccount()) — AccountsController.getAccount()
- Consumer ids arrive as long on the public API but are converted to String for the aggregate id, which is fixed via SaveOptions().withId(aggregateId) — AccountingService.create(), AccountingServiceCommandHandler.makeAuthorizeCommandInternal()
- AccountingEventConsumer.domainEventHandlers() carries a TODO comment explaining the "correct package" hack for the Consumer aggregate type string — AccountingEventConsumer.domainEventHandlers()

## Legacy Notes
- none found

## Related Skills
| Domain | Relationship | Reason |
|--------|-------------|--------|
| consumer-management | calls | AccountingServiceCommandHandler.authorize() / reverseAuthorization() are invoked as saga steps following ConsumerService.validateOrderForConsumer() to authorize payment against the consumer account established at consumer registration. |

## AI Agent Instructions
1. Before changing any command-handling logic, check that the public saga command (AuthorizeCommand, ReverseAuthorizationCommand, ReviseAuthorization) is still translated to its *Internal counterpart and that the AccountDisabledException catching clause is preserved — AccountingServiceCommandHandler.authorize(), reverseAuthorization(), reviseAuthorization()
2. Never break the contract that authorize emits AccountAuthorizedEvent while reverse and revise emit no events; downstream saga choreography depends on this asymmetry — Account.process(AuthorizeCommandInternal), Account.process(ReverseAuthorizationCommandInternal), Account.process(ReviseAuthorizationCommandInternal)
3. Any change to the channel name "accountingService" or to the consumer-id-as-aggregate-id convention will break the order saga and the consumer-service event subscription; coordinate changes with the consumer-service and order-service skills — AccountingServiceChannels.accountingServiceChannel, AccountingEventConsumer.createAccount()
4. Run the existing integration test which boots an in-memory saga, publishes ConsumerCreated, then sends an AuthorizeCommand and asserts a reply — AccountingServiceCommandHandlerTest.shouldReply()
5. Do not add @Entity / JPA persistence to Account; it is an Eventuate ReflectiveMutableCommandProcessingAggregate persisted via EventuateAggregateStore, and new state must be expressed as a process/apply pair on a new event — Account, AccountServiceConfiguration.accountRepositorySync()
