from importlib.metadata import version, metadata

__project_name__ = "mediawiki-file-skimmer"
name = metadata(__project_name__)['Name']
__version__ = version(__project_name__)
__user_agent__ = f"{name}/{__version__}"