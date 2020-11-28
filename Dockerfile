FROM python:3.7.9-buster

ARG SCRIPT_NAME
ADD $SCRIPT_NAME $SCRIPT_NAME
ADD database.py database.py
ADD requirements.txt requirements.txt

RUN pip install -r requirements.txt
ENV SCRIPT_NAME=$SCRIPT_NAME

CMD python $SCRIPT_NAME
