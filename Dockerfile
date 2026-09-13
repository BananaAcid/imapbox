FROM python:3.13-slim-bookworm

WORKDIR /opt/bin/

# Copy source files
COPY *.py .
COPY requirements.txt .
COPY VERSION .
COPY hook-addToElasticSearch.sh /etc/imapbox/.
COPY hook-notifyOnDiscord.py /etc/imapbox/.
COPY example-config.cfg /etc/imapbox/config.cfg

# Remove the local_folder line
RUN sed -i '/^local_folder=/d' /etc/imapbox/config.cfg && sed -i '/^wkhtmltopdf=/d' /etc/imapbox/config.cfg

# Make the hooks executable, in case they will be needed
RUN chmod +x /etc/imapbox/hook-addToElasticSearch.sh /etc/imapbox/hook-notifyOnDiscord.py

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y wkhtmltopdf curl

# Make the data and config directory a volume
VOLUME ["/etc/imapbox/"]
VOLUME ["/var/imapbox/"]

# Set entry point

ENTRYPOINT ["python", "./imapbox.py"]
