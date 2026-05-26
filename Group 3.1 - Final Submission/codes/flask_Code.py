import flask
from flask import Flask, request

app = Flask(__name__)

@app.route('/speed')
def speed():
    value = request.args.get('value')
    (f"Received speed value: {value}")
    return f"Speed set to {value}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)