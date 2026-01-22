"""

This module contains a collection of string templates designed to streamline the integration
of features like attachments into the LLM request.

"""

TEXT_ATTACHMENT_TEMPLATE = (
    """Below is the content of {attachment_name}:\n\n{attachment_parsed_content}"""
)
URL_ATTACHMENT_TEMPLATE = (
    """Assume you can access the external URL {attachment_name}. """
    """Use the URL's content below to respond to the queries:\n\n{content}"""
)
IMAGE_VISION_ATTACHMENT_TEMPLATE = (
    """I have uploaded an image ({filename}). """
    """Assume that you can see the attached image. """
    """First, read the image analysis:\n\n"""
    """<image_analysis>{parsed_image_description}</image_analysis>\n\n"""
    """Use any relevant parts to inform your response. """
    """Do NOT reference the image analysis in your response. """
    """Respond in the same language as my next message. """
)
