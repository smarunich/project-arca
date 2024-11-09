# Dockerfile

FROM python:3.9-slim

# Install necessary packages
RUN pip install --no-cache-dir kopf kubernetes

# Copy your agent code
COPY agent.py /agent.py

# Set the working directory
WORKDIR /

# Define the entrypoint
ENTRYPOINT ["kopf", "run", "--standalone", "/agent.py"]
