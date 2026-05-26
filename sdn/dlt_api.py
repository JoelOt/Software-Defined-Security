"""
Small local API used by NetworkOrchestrator to inject runtime DLT data.

The API only binds to localhost by default and receives generated controller
accounts at runtime, so no private keys need to live in the repository.
"""
import os

from flask import Flask, jsonify, request


app = Flask(__name__)
controller = None


@app.route('/DLT_info', methods=['POST'])
def receive_dlt_info():
    if controller is None:
        return jsonify({'error': 'controller not initialized'}), 503

    payload = request.get_json(silent=True) or {}
    required_fields = {'address', 'private_key', 'eth_node', 'contract_address', 'abi'}
    missing_fields = sorted(required_fields - set(payload))
    if missing_fields:
        return jsonify({'error': 'missing required fields', 'fields': missing_fields}), 400

    controller.init_stats(payload)
    return jsonify({'message': 'DLT info loaded'})


def init(sdn_controller):
    global controller
    controller = sdn_controller
    host = os.environ.get('SDN_API_HOST', '127.0.0.1')
    app.run(debug=False, host=host, port=controller.get_port_number(), use_reloader=False)
