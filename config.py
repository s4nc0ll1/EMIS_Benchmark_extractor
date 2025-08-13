"""
This class is used for centralized configuration
"""

class Config:
    """
    Configuration data used all over the API.
    """

    _Config__conf = {
        "EMIS": {
            "token": "" # Placeholder for EMIS Token
        },
    }

    @staticmethod
    def get_emis_config(): # Getter for EMIS config
        return Config._Config__conf["EMIS"]
