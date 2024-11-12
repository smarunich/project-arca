# ARCA Demo Guide

This guide provides instructions for demonstrating ARCA's capabilities in automating TSB resource management.

## Quick Start

The easiest way to run the demo is using the provided demo script:

```bash
# Run with default namespace (bookinfo)
./demo.sh

# Run with custom namespace
./demo.sh -n my-demo
```

## Demo Script Features

The demo script (`demo.sh`) provides:
- Interactive step-by-step demonstration
- Clear visual feedback
- Automatic resource creation
- Status checking
- Pretty-printed results

## Demo Flow

1. **Namespace Creation**
   - Creates a new namespace
   - Labels it for ARCA management
   - Triggers workspace creation in TSB

2. **Application Deployment**
   - Deploys Bookinfo application
   - Creates necessary services
   - Sets up service accounts

3. **Service Exposure**
   - Exposes services via annotations
   - Configures gateway routes
   - Sets up domain mappings

4. **Results Display**
   - Shows service annotations
   - Displays gateway status
   - Lists access URLs

## Example Service Configuration

```yaml
apiVersion: v1
kind: Service
metadata:
  name: productpage
  annotations:
    arca.io/expose: "true"
    arca.io/domain: "bookinfo.example.com"
    arca.io/path: "/productpage"
spec:
  ports:
    - port: 9080
  selector:
    app: productpage
```

## Access Information

After running the demo:
1. Get the gateway IP
2. Add DNS entries or update /etc/hosts
3. Access services via configured domains

## Cleanup

To remove demo resources:
```bash
kubectl delete namespace <namespace-name>
```

## Next Steps
- Explore service annotations
- Configure custom routes
- Set up additional gateways
- Monitor TSB resources
