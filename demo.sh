#!/bin/bash

# Colors and formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Default namespace
NAMESPACE="bookinfo"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            error "Unknown argument: $1"
            ;;
    esac
done

# Function to show success message
function success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to show error message
function error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

# Function to show info message
function info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Function to show header
function show_header() {
    echo -e "\n${BOLD}$1${NC}"
    echo -e "${BLUE}$(printf '=%.0s' {1..50})${NC}\n"
}

# Function to wait for user input
function wait_for_user() {
    echo -e "\n${YELLOW}Press Enter to continue...${NC}"
    read
}

# Show ARCA logo and info
function show_logo() {
    clear
    echo -e "${BOLD}${BLUE}"
    cat << "EOF"
 █████╗ ██████╗  ██████╗ █████╗     ██████╗ ███████╗███╗   ███╗ ██████╗ 
██╔══██╗██╔══██╗██╔════╝██╔══██╗    ██╔══██╗██╔════╝████╗ ████║██╔═══██╗
███████║██████╔╝██║     ███████║    ██║  ██║█████╗  ██╔████╔██║██║   ██║
██╔══██║██╔══██╗██║     ██╔══██║    ██║  ██║██╔══╝  ██║╚██╔╝██║██║   ██║
██║  ██║██║  ██║╚██████╗██║  ██║    ██████╔╝███████╗██║ ╚═╝ ██║╚██████╔╝
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝    ╚═════╝ ╚══════╝╚═╝     ╚═╝ ╚═════╝ 
EOF
    echo -e "${NC}"
    echo -e "Automated Resource and Configuration Assistant Demo"
    echo -e "Using namespace: ${YELLOW}${NAMESPACE}${NC}\n"
}

# Download Bookinfo application
function download_bookinfo() {
    show_header "Downloading Bookinfo Application"
    
    info "Downloading bookinfo.yaml..."
    curl -sO https://raw.githubusercontent.com/tetratecx/library/main/apps/bookinfo/bookinfo.yaml
    success "Downloaded bookinfo.yaml"
}

# Step 1: Create namespace
function step1_create_namespace() {
    show_header "Step 1: Create Application Namespace"
    
    cat << EOF
# Create namespace
apiVersion: v1
kind: Namespace
metadata:
  name: ${NAMESPACE}
EOF
    
    wait_for_user
    kubectl create namespace ${NAMESPACE}
    success "Created namespace: ${NAMESPACE}"
}

# Step 2: Enable ARCA management
function step2_enable_management() {
    show_header "Step 2: Enable ARCA Management"
    
    cat << EOF
# Label namespace for ARCA management
kubectl label namespace ${NAMESPACE} arca.io/managed=true
EOF
    
    wait_for_user
    kubectl label namespace ${NAMESPACE} arca.io/managed=true
    success "Enabled ARCA management"
    
    info "Waiting for TSB workspace creation..."
    sleep 5
}

# Step 3: Deploy application
function step3_deploy_app() {
    show_header "Step 3: Deploy Application"
    
    cat << EOF
# Deploy Bookinfo application
kubectl apply -f bookinfo.yaml -n ${NAMESPACE}
EOF
    
    wait_for_user
    kubectl apply -f bookinfo.yaml -n ${NAMESPACE}
    success "Deployed application"
}

# Step 4: Expose services
function step4_expose_services() {
    show_header "Step 4: Expose Services"
    
    cat << EOF
# Expose productpage service
kubectl annotate service productpage -n ${NAMESPACE} \
    arca.io/expose=true \
    arca.io/domain=${NAMESPACE}.example.com \
    arca.io/path=/productpage

# Expose reviews service
kubectl annotate service reviews -n ${NAMESPACE} \
    arca.io/expose=true \
    arca.io/domain=reviews.${NAMESPACE}.example.com \
    arca.io/path=/reviews

# Expose ratings service
kubectl annotate service ratings -n ${NAMESPACE} \
    arca.io/expose=true \
    arca.io/domain=ratings.${NAMESPACE}.example.com \
    arca.io/path=/ratings
EOF
    
    wait_for_user
    
    # Expose productpage
    kubectl annotate service productpage -n ${NAMESPACE} \
        arca.io/expose=true \
        arca.io/domain=${NAMESPACE}.example.com \
        arca.io/path=/productpage
    success "Exposed productpage service"
    
    # Expose reviews
    kubectl annotate service reviews -n ${NAMESPACE} \
        arca.io/expose=true \
        arca.io/domain=reviews.${NAMESPACE}.example.com \
        arca.io/path=/reviews
    success "Exposed reviews service"
    
    # Expose ratings
    kubectl annotate service ratings -n ${NAMESPACE} \
        arca.io/expose=true \
        arca.io/domain=ratings.${NAMESPACE}.example.com \
        arca.io/path=/ratings
    success "Exposed ratings service"
    
    info "Waiting for gateway configurations..."
    sleep 5
}

# Step 5: Show results
function step5_show_results() {
    show_header "Step 5: Results"
    
    echo -e "${BOLD}Service Annotations${NC}"
    echo -e "${BLUE}$(printf '=%.0s' {1..50})${NC}\n"
    
    # Function to show service annotations
    function show_service_annotations() {
        local svc=$1
        echo -e "${BOLD}${BLUE}$svc Service:${NC}"
        echo -e "${YELLOW}ARCA Configuration:${NC}"
        
        # Get annotations in a format jq can process
        local annotations=$(kubectl get service $svc -n ${NAMESPACE} -o=json | jq -r '.metadata.annotations')
        
        if [[ "$annotations" != "null" ]]; then
            # Format exposure settings
            echo -e "  ${GREEN}Exposure:${NC}"
            echo -e "    Domain  : $(echo $annotations | jq -r '."arca.io/domain" // "Not set"')"
            echo -e "    Path    : $(echo $annotations | jq -r '."arca.io/path" // "Not set"')"
            echo -e "    Gateway : $(echo $annotations | jq -r '."arca.io/gateway" // "Not set"')"
            
            # Format status
            echo -e "  ${GREEN}Status:${NC}"
            echo -e "    State   : $(echo $annotations | jq -r '."arca.io/status" // "Not set"')"
            echo -e "    URL     : $(echo $annotations | jq -r '."arca.io/url" // "Not set"')"
        else
            echo -e "  ${RED}No ARCA annotations found${NC}"
        fi
        echo
    }
    
    # Show annotations for each service
    for svc in productpage reviews ratings; do
        show_service_annotations $svc
        if [ "$svc" != "ratings" ]; then
            echo -e "${BLUE}$(printf '=%.0s' {1..30})${NC}\n"
        fi
    done
    
    echo -e "\n${BOLD}Resource Summary:${NC}"
    echo -e "${BLUE}$(printf '=%.0s' {1..50})${NC}\n"
    
    echo -e "${YELLOW}Namespace Labels:${NC}"
    kubectl get namespace ${NAMESPACE} -o=json | jq -r '.metadata.labels // {}'
    
    echo -e "\n${YELLOW}Service Routes:${NC}"
    for svc in productpage reviews ratings; do
        local url=$(kubectl get service $svc -n ${NAMESPACE} -o=json | jq -r '.metadata.annotations."arca.io/url" // empty')
        if [[ -n "$url" ]]; then
            echo -e "  ${BLUE}$svc${NC} -> $url"
        fi
    done
}

# Main demo flow
show_logo
download_bookinfo
step1_create_namespace
step2_enable_management
step3_deploy_app
step4_expose_services
step5_show_results

show_header "Demo Complete"
info "Access the applications at:"
echo -e "- http://${NAMESPACE}.example.com/productpage"
echo -e "- http://reviews.${NAMESPACE}.example.com/reviews"
echo -e "- http://ratings.${NAMESPACE}.example.com/ratings"

echo -e "\n${YELLOW}Note: Add the following entries to your /etc/hosts file:${NC}"
echo -e "$(kubectl get service -n ${NAMESPACE} arca-gateway -o=jsonpath='{.status.loadBalancer.ingress[0].ip}') ${NAMESPACE}.example.com reviews.${NAMESPACE}.example.com ratings.${NAMESPACE}.example.com"