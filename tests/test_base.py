from fastapi_poe.base import PoeBot
from fastapi_poe.templates import (
    IMAGE_VISION_ATTACHMENT_TEMPLATE,
    TEXT_ATTACHMENT_TEMPLATE,
    URL_ATTACHMENT_TEMPLATE,
)
from fastapi_poe.types import Attachment, ProtocolMessage, QueryRequest


class TestPoeBot:
    def test_insert_attachment_messages(self) -> None:
        # Create mock attachments
        mock_text_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/text/test.txt",
            name="test.txt",
            content_type="text/plain",
            parsed_content="Hello, world!",
        )
        mock_image_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/image/test.png",
            name="test.png",
            content_type="image/png",
            parsed_content="test.png***Hello, world!",
        )
        mock_image_attachment_2 = Attachment(
            url="https://pfst.cf2.poecdn.net/base/image/test.png",
            name="testimage2.jpg",
            content_type="image/jpeg",
            parsed_content="Hello, world!",
        )
        mock_pdf_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/application/test.pdf",
            name="test.pdf",
            content_type="application/pdf",
            parsed_content="Hello, world!",
        )
        mock_html_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/text/test.html",
            name="test.html",
            content_type="text/html",
            parsed_content="Hello, world!",
        )
        mock_video_attachment = Attachment(
            url="https://pfst.cf2.poecdn.net/base/video/test.mp4",
            name="test.mp4",
            content_type="video/mp4",
            parsed_content="Hello, world!",
        )
        # Create mock protocol messages
        message_without_attachments = ProtocolMessage(
            role="user", content="Hello, world!"
        )
        message_with_attachments = ProtocolMessage(
            role="user",
            content="Here's some attachments",
            attachments=[
                mock_text_attachment,
                mock_image_attachment,
                mock_image_attachment_2,
                mock_pdf_attachment,
                mock_html_attachment,
                mock_video_attachment,
            ],
        )
        # Create mock query request
        mock_query_request = QueryRequest(
            version="1.0",
            type="query",
            query=[message_without_attachments, message_with_attachments],
            user_id="123",
            conversation_id="123",
            message_id="456",
        )

        assert (
            mock_image_attachment.parsed_content
        )  # satisfy pyright so split() works below
        expected_protocol_messages = [
            message_without_attachments,
            ProtocolMessage(
                role="user",
                content=TEXT_ATTACHMENT_TEMPLATE.format(
                    attachment_name=mock_text_attachment.name,
                    attachment_parsed_content=mock_text_attachment.parsed_content,
                ),
            ),
            ProtocolMessage(
                role="user",
                content=TEXT_ATTACHMENT_TEMPLATE.format(
                    attachment_name=mock_pdf_attachment.name,
                    attachment_parsed_content=mock_pdf_attachment.parsed_content,
                ),
            ),
            ProtocolMessage(
                role="user",
                content=URL_ATTACHMENT_TEMPLATE.format(
                    attachment_name=mock_html_attachment.name,
                    content=mock_html_attachment.parsed_content,
                ),
            ),
            ProtocolMessage(
                role="user",
                content=IMAGE_VISION_ATTACHMENT_TEMPLATE.format(
                    filename=mock_image_attachment.parsed_content.split("***")[0],
                    parsed_image_description=mock_image_attachment.parsed_content.split(
                        "***"
                    )[1],
                ),
            ),
            ProtocolMessage(
                role="user",
                content=IMAGE_VISION_ATTACHMENT_TEMPLATE.format(
                    filename=mock_image_attachment_2.name,
                    parsed_image_description=mock_image_attachment_2.parsed_content,
                ),
            ),
            message_with_attachments,
        ]

        # Test the insert_attachment_messages method
        bot = PoeBot(bot_name="test_bot")
        modified_query_request = bot.insert_attachment_messages(mock_query_request)
        protocol_messages = modified_query_request.query

        assert protocol_messages == expected_protocol_messages
