import requests

WIKIDOT_URI = "https://dnd5e.wikidot.com"

def api_call(uri: str) -> dict:
    """
    Returns html content for URI request
    Args:
        uri: Address to query against

    Returns:
        HTML content of requested web page

    Raises:
        AssertionError: raised if a 200 status code is not returned
    """
    req = requests.get(uri)

    assert req.status_code == 200

    return req.content
