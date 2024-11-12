# ARCA User Stories

## Namespace Management

### As a Platform Engineer
1. I want namespaces to be automatically managed in TSB when labeled
   - Given a namespace with the ARCA label
   - When the namespace is created or updated
   - Then a corresponding TSB workspace should be created/updated

2. I want workspace settings to be consistently configured
   - Given a managed namespace
   - When its workspace is created
   - Then standard security and gateway settings should be applied

### As a Developer
1. I want to expose my services through TSB gateways
   - Given a service in a managed namespace
   - When I add ARCA annotations
   - Then the service should be exposed through a TSB gateway

2. I want to see the status of my service exposure
   - Given an exposed service
   - When I check the service annotations
   - Then I should see the exposure status and URL

## Gateway Management

### As a Platform Engineer
1. I want standardized gateway configurations
   - Given a managed namespace
   - When a gateway is created
   - Then it should follow organization standards

2. I want automated gateway lifecycle management
   - Given a managed workspace
   - When services are exposed
   - Then gateways should be automatically created/updated

### As a Developer
1. I want simple service exposure configuration
   - Given a Kubernetes service
   - When I add ARCA annotations
   - Then routing should be automatically configured

2. I want to customize gateway routes
   - Given an exposed service
   - When I update annotations
   - Then routing rules should be updated

## Security Management

### As a Security Engineer
1. I want consistent security policies
   - Given a managed workspace
   - When it's created
   - Then standard security settings should be applied

2. I want automated mTLS configuration
   - Given a managed service
   - When it's exposed
   - Then mTLS should be properly configured

## Monitoring and Operations

### As an Operations Engineer
1. I want visibility into ARCA operations
   - Given ARCA components
   - When they perform operations
   - Then detailed logs should be available

2. I want automated reconciliation
   - Given configuration drift
   - When detected
   - Then resources should be automatically reconciled 