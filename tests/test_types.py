import pydantic
import pytest
from fastapi_poe.types import (
    CostItem,
    CustomCallDefinition,
    CustomToolDefinition,
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


class TestCustomToolDefinition:

    def test_basic_instantiation(self) -> None:
        """Test creating CustomToolDefinition with alias 'format'"""
        tool = CustomToolDefinition(
            name="my_tool",
            description="A custom tool",
            format={"type": "object", "properties": {}},
        )
        assert tool.name == "my_tool"
        assert tool.description == "A custom tool"
        assert tool.format_ == {"type": "object", "properties": {}}

    def test_field_name_works_with_populate_by_name(self) -> None:
        """Test that 'format_' field name also works due to populate_by_name=True"""
        tool = CustomToolDefinition(
            name="my_tool",
            description="A custom tool",
            format_={"type": "string"},  # type: ignore
        )
        assert tool.format_ == {"type": "string"}

    def test_requires_name_field(self) -> None:
        """Test that name field is required"""
        with pytest.raises(pydantic.ValidationError):
            CustomToolDefinition()  # type: ignore

    def test_optional_fields(self) -> None:
        """Test that description and format are optional"""
        tool = CustomToolDefinition(name="my_tool")
        assert tool.name == "my_tool"
        assert tool.description is None
        assert tool.format_ is None

    def test_with_only_name_and_description(self) -> None:
        """Test with only name and description"""
        tool = CustomToolDefinition(name="tool", description="desc")
        assert tool.name == "tool"
        assert tool.description == "desc"
        assert tool.format_ is None

    def test_with_only_name_and_format(self) -> None:
        """Test with only name and format"""
        tool = CustomToolDefinition(name="tool", format={"type": "string"})
        assert tool.name == "tool"
        assert tool.description is None
        assert tool.format_ == {"type": "string"}

    def test_serialization_uses_alias(self) -> None:
        """Test that serialization uses 'format' not 'format_'"""
        tool = CustomToolDefinition(
            name="my_tool", description="desc", format={"key": "value"}
        )
        data = tool.model_dump(by_alias=True)
        assert "format" in data
        assert "format_" not in data
        assert data["format"] == {"key": "value"}

    def test_serialization_without_alias(self) -> None:
        """Test that serialization without by_alias uses 'format_'"""
        tool = CustomToolDefinition(
            name="my_tool", description="desc", format={"key": "value"}
        )
        data = tool.model_dump(by_alias=False)
        assert "format_" in data
        assert "format" not in data
        assert data["format_"] == {"key": "value"}

    def test_json_serialization(self) -> None:
        """Test JSON serialization with alias"""
        tool = CustomToolDefinition(
            name="tool", description="desc", format={"nested": "data"}
        )
        json_str = tool.model_dump_json(by_alias=True)
        assert '"format"' in json_str
        assert '"format_"' not in json_str

    def test_deserialization_from_json(self) -> None:
        """Test deserializing from JSON with alias"""
        json_data = {
            "name": "tool1",
            "description": "A tool",
            "format": {"type": "array"},
        }
        tool = CustomToolDefinition(**json_data)
        assert tool.name == "tool1"
        assert tool.format_ == {"type": "array"}

    def test_invalid_type_for_format(self) -> None:
        """Test that format must be a dict"""
        with pytest.raises(pydantic.ValidationError):
            CustomToolDefinition(name="tool", description="desc", format="not a dict")  # type: ignore


class TestCustomCallDefinition:

    def test_basic_instantiation(self) -> None:
        """Test creating CustomCallDefinition with alias 'input'"""
        call = CustomCallDefinition(name="my_tool", input='{"arg": "value"}')
        assert call.name == "my_tool"
        assert call.input_ == '{"arg": "value"}'

    def test_field_name_works_with_populate_by_name(self) -> None:
        """Test that 'input_' field name also works due to populate_by_name=True"""
        call = CustomCallDefinition(name="my_tool", input_='{"data": 123}')  # type: ignore
        assert call.input_ == '{"data": 123}'

    def test_requires_all_fields(self) -> None:
        """Test that all required fields are validated"""
        with pytest.raises(pydantic.ValidationError):
            CustomCallDefinition(name="my_tool")  # type: ignore

        with pytest.raises(pydantic.ValidationError):
            CustomCallDefinition(input="data")  # type: ignore

    def test_serialization_uses_alias(self) -> None:
        """Test that serialization uses 'input' not 'input_'"""
        call = CustomCallDefinition(name="tool1", input="test_input")
        data = call.model_dump(by_alias=True)
        assert "input" in data
        assert "input_" not in data
        assert data["input"] == "test_input"

    def test_serialization_without_alias(self) -> None:
        """Test that serialization without by_alias uses 'input_'"""
        call = CustomCallDefinition(name="tool1", input="test_input")
        data = call.model_dump(by_alias=False)
        assert "input_" in data
        assert "input" not in data
        assert data["input_"] == "test_input"

    def test_json_serialization(self) -> None:
        """Test JSON serialization with alias"""
        call = CustomCallDefinition(name="calculator", input='{"operation": "add"}')
        json_str = call.model_dump_json(by_alias=True)
        assert '"input"' in json_str
        assert '"input_"' not in json_str

    def test_deserialization_from_json(self) -> None:
        """Test deserializing from JSON with alias"""
        json_data = {
            "name": "calculator",
            "input": '{"operation": "add", "a": 1, "b": 2}',
        }
        call = CustomCallDefinition(**json_data)
        assert call.name == "calculator"
        assert call.input_ == '{"operation": "add", "a": 1, "b": 2}'
