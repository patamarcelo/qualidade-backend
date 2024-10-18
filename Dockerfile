# Use the official Python image from Docker Hub
FROM python:3.10-slim

# Set the working directory to /app
WORKDIR /app

# Install system dependencies for Pillow and any other needed libraries
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    tk-dev \
    build-essential \
    && apt-get clean

# Copy the requirements.txt file
COPY requirements.txt /app/

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app/

# Collect static files (if applicable)
RUN python manage.py collectstatic --noinput

# Set environment variables (optional, depending on your app setup)
ENV PORT 8000

# Expose port 8000 to the outside world
EXPOSE 8000

# Run the Django application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "qualidade_project.wsgi:application"]