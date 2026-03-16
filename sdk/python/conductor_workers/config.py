"""
Conductor configuration and client setup
"""
from conductor.client.configuration.configuration import Configuration
from conductor.client.orkes_clients import OrkesClients

# Configuration for Conductor server
CONDUCTOR_SERVER_URL = "http://localhost:8080/api"

def get_conductor_client():
    """Get configured Conductor client"""
    config = Configuration(
        server_api_url=CONDUCTOR_SERVER_URL,
        debug=True
    )
    return OrkesClients(configuration=config)
