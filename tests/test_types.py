import pydantic
import pytest
from fastapi_poe.types import (
    CostItem,
    MessageReaction,
    PartialResponse,
    ProtocolMessage,
    QueryRequest,
    Sender,
    SettingsResponse,
    User,
)


class TestSettingsResponse:

    def test_default_response_version(self) -> None:
        response = SettingsResponse()
        assert response.response_version == 2


def test_extra_attrs() -> None:
    with pytest.raises(pydantic.ValidationError):
        PartialResponse(text="hi", replaceResponse=True)  # type: ignore

    resp = PartialResponse(text="a capybara", is_replace_response=True)
    assert resp.is_replace_response is True
    assert resp.text == "a capybara"


def test_cost_item() -> None:
    with pytest.raises(pydantic.ValidationError):
        CostItem(amount_usd_milli_cents="1")  # type: ignore

    item = CostItem(amount_usd_milli_cents=25)
    assert item.amount_usd_milli_cents == 25
    assert item.description is None

    item = CostItem(amount_usd_milli_cents=25.5, description="Test")  # type: ignore
    assert item.amount_usd_milli_cents == 26
    assert item.description == "Test"


class TestSender:

    def test_sender_basic(self) -> None:
        sender = Sender()
        assert sender.id is None
        assert sender.name is None

    def test_sender_with_id(self) -> None:
        sender = Sender(id="user123")
        assert sender.id == "user123"
        assert sender.name is None

    def test_sender_with_name(self) -> None:
        sender = Sender(name="TestBot")
        assert sender.id is None
        assert sender.name == "TestBot"

    def test_sender_with_all_fields(self) -> None:
        sender = Sender(id="bot456", name="MyBot")
        assert sender.id == "bot456"
        assert sender.name == "MyBot"


class TestUser:

    def test_user_basic(self) -> None:
        user = User(id="user123")
        assert user.id == "user123"
        assert user.name is None

    def test_user_with_name(self) -> None:
        user = User(id="user456", name="Alice")
        assert user.id == "user456"
        assert user.name == "Alice"

    def test_user_requires_id(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            User()  # type: ignore


class TestMessageReaction:

    def test_reaction_basic(self) -> None:
        reaction = MessageReaction(user_id="user123", reaction="like")
        assert reaction.user_id == "user123"
        assert reaction.reaction == "like"

    def test_reaction_requires_user_id(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MessageReaction(reaction="like")  # type: ignore

    def test_reaction_requires_reaction(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            MessageReaction(user_id="user123")  # type: ignore


class TestProtocolMessage:

    def test_protocol_message_basic(self) -> None:
        msg = ProtocolMessage(role="user", sender=Sender(), content="Hello, world!")
        assert msg.role == "user"
        assert isinstance(msg.sender, Sender)
        assert msg.content == "Hello, world!"
        assert msg.reactions == []
        assert msg.referenced_message is None

    def test_protocol_message_with_reactions(self) -> None:
        msg = ProtocolMessage(
            role="user",
            sender=Sender(),
            content="Hello!",
            reactions=[
                MessageReaction(user_id="user1", reaction="like"),
                MessageReaction(user_id="user2", reaction="dislike"),
            ],
        )
        assert len(msg.reactions) == 2
        assert msg.reactions[0].user_id == "user1"
        assert msg.reactions[0].reaction == "like"
        assert msg.reactions[1].user_id == "user2"
        assert msg.reactions[1].reaction == "dislike"

    def test_protocol_message_with_referenced_message(self) -> None:
        referenced_msg = ProtocolMessage(
            role="user",
            sender=Sender(),
            content="Original message",
            message_id="msg123",
        )
        reply_msg = ProtocolMessage(
            role="bot",
            sender=Sender(),
            content="Reply to original",
            referenced_message=referenced_msg,
        )
        assert reply_msg.referenced_message is not None
        assert reply_msg.referenced_message.content == "Original message"
        assert reply_msg.referenced_message.message_id == "msg123"

    def test_protocol_message_optional_sender(self) -> None:
        # Sender is now optional
        msg = ProtocolMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.sender is None
        assert msg.content == "Hello"

    def test_protocol_message_nested_referenced_message(self) -> None:
        # Test deeply nested referenced messages
        msg1 = ProtocolMessage(
            role="user", sender=Sender(), content="First message", message_id="msg1"
        )
        msg2 = ProtocolMessage(
            role="bot",
            sender=Sender(),
            content="Second message",
            message_id="msg2",
            referenced_message=msg1,
        )
        msg3 = ProtocolMessage(
            role="user",
            sender=Sender(),
            content="Third message",
            message_id="msg3",
            referenced_message=msg2,
        )
        assert msg3.referenced_message is not None
        assert msg3.referenced_message.message_id == "msg2"
        assert msg3.referenced_message.referenced_message is not None
        assert msg3.referenced_message.referenced_message.message_id == "msg1"

    def test_protocol_message_with_sender_object(self) -> None:
        sender = Sender(id="user123", name="TestUser")
        msg = ProtocolMessage(role="user", sender=sender, content="Hello, world!")
        assert msg.role == "user"
        assert msg.sender == sender
        assert msg.sender is not None
        assert msg.sender.id == "user123"
        assert msg.sender.name == "TestUser"
        assert msg.content == "Hello, world!"


class TestQueryRequest:

    def test_query_request_with_users(self) -> None:
        query_request = QueryRequest(
            version="1.0",
            type="query",
            query=[ProtocolMessage(role="user", sender=Sender(), content="Hello")],
            user_id="user123",
            conversation_id="conv456",
            message_id="msg789",
            users=[User(id="user1", name="Alice"), User(id="user2", name="Bob")],
        )
        assert len(query_request.users) == 2
        assert query_request.users[0].id == "user1"
        assert query_request.users[0].name == "Alice"
        assert query_request.users[1].id == "user2"
        assert query_request.users[1].name == "Bob"

    def test_query_request_empty_users(self) -> None:
        query_request = QueryRequest(
            version="1.0",
            type="query",
            query=[ProtocolMessage(role="user", sender=Sender(), content="Hello")],
            user_id="user123",
            conversation_id="conv456",
            message_id="msg789",
        )
        assert query_request.users == []

    def test_query_request_with_reactions_in_messages(self) -> None:
        query_request = QueryRequest(
            version="1.0",
            type="query",
            query=[
                ProtocolMessage(
                    role="user",
                    sender=Sender(id="user1"),
                    content="Hello",
                    reactions=[MessageReaction(user_id="user2", reaction="like")],
                )
            ],
            user_id="user123",
            conversation_id="conv456",
            message_id="msg789",
        )
        assert len(query_request.query[0].reactions) == 1
        assert query_request.query[0].reactions[0].reaction == "like"
