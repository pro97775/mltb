FROM pro97775/mltb-prebuild:aria2qbit

WORKDIR /app
RUN chmod 777 /app

RUN python3 -m venv appenv

COPY requirements.txt .
RUN appenv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .
RUN sed -i 's/\r$//' *.sh && chmod +x *.sh

CMD ["bash", "start.sh"]
