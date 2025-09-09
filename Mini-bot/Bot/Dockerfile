FROM python:3.11-slim-buster

# Install git so the bot can push changes back to GitHub
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# The user is providing the code via a bind mount, so we only need to install
# the dependencies listed in requirements.txt. We'll copy this file into the
# image to ensure the dependencies are installed correctly.
COPY requirements.txt .

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# The command to run the bot. This will execute when the container starts.
# Since the code is in a bind mount, it will be immediately available.
CMD ["python", "Messagebot.py"]
# Use the official Python image from Docker Hub, specifying the exact version
FROM python:3.11-slim

# Install git so the bot can push changes back to GitHub
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# The user is providing the code via a bind mount, so we only need to install
# the dependencies listed in requirements.txt. We'll copy this file into the
# image to ensure the dependencies are installed correctly.
COPY requirements.txt .

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# The command to run the bot. This will execute when the container starts.
# Since the code is in a bind mount, it will be immediately available.
CMD ["python", "Messagebot.py"]
