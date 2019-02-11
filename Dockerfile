FROM python:3.6-jessie

WORKDIR /app

COPY requirements.txt /app/
COPY python.py /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD [ "python", "/app/python.py", "-c", "/app/config.yaml" ] 

