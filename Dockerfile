FROM python:3.9

# Prevent python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Flask and other likely dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask autogen-agentchat
RUN git config --global --add safe.directory '*'

# Set a working directory
WORKDIR /workspace
