# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Create a non-root user (Hugging Face Spaces requirement)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY --chown=user . .

# Hugging Face Spaces exposes port 7860 for web servers
EXPOSE 7860
ENV PORT=7860

# Run the bot
CMD ["python", "bot.py"]
