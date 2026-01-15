#!/bin/bash

# Script to run LiminalQA in Docker container

echo "Starting LiminalQA in Docker container..."

# Build the Docker image
echo "Building Docker image..."
docker build -t liminalqa .

if [ $? -ne 0 ]; then
    echo "Error: Failed to build Docker image"
    exit 1
fi

echo "Docker image built successfully!"

# Create necessary directories
mkdir -p data reports plans

# Run the container
echo "Starting container..."
docker run -it --rm \
    -v $(pwd)/data:/app/data \
    -v $(pwd)/reports:/app/reports \
    -v $(pwd)/plans:/app/plans \
    liminalqa "$@"

echo "Container exited."