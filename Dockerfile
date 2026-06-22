FROM python:3.11-slim

WORKDIR /app

# Copy the entire space repository into the Docker container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Make the startup script executable
RUN chmod +x start_all.sh

# Run the supervisor script
CMD ["bash", "start_all.sh"]
