FROM python:3.7.9-buster

ARG SCRIPT_NAME
ADD $SCRIPT_NAME $SCRIPT_NAME
ADD database.py database.py

CMD python3 $SCRIPT_NAME
