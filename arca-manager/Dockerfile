# Dockerfile

FROM python:3.12-slim

# Install necessary packages
RUN pip install --no-cache-dir kopf kubernetes

# Copy your manager code

COPY manager.py /manager.py


# Set the working directory
WORKDIR /

# Define the entrypoint
ENTRYPOINT ["kopf", "run", "--standalone", "/manager.py"]
