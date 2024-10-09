# Base image
FROM python:alpine3.20

# Copy files to app in docker image
COPY . /app

# Change dir
WORKDIR /app

# Install dependencies
RUN pip install -r requirements.txt

# Start command when container runs
CMD [ "python", "scrubbot.py" ]
