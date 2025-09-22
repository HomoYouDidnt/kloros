# KLoROS Speaker Recognition System

The KLoROS speaker recognition system allows the AI to identify users by their voice, enabling personalized interactions and user-specific responses.

## Features

- **Voice Enrollment**: Users can enroll their voice using KLoROS-branded sentences
- **Speaker Identification**: Automatic identification of known speakers after wake word detection
- **Name Verification**: Spell-out verification to ensure correct name spelling
- **User Management**: Commands to list, enroll, and delete voice profiles
- **Multiple Backends**: Support for both mock (testing) and embedding-based (production) backends

## Configuration

Set these environment variables to enable and configure speaker recognition:

```bash
# Enable speaker recognition (0=disabled, 1=enabled)
export KLR_ENABLE_SPEAKER_ID=1

# Choose backend ("mock" for testing, "embedding" for production)
export KLR_SPEAKER_BACKEND=mock

# Set recognition threshold (0.0-1.0, higher = more strict)
export KLR_SPEAKER_THRESHOLD=0.8

# Optional: Set custom database path for embedding backend
export KLR_SPEAKER_DB_PATH=/path/to/speaker_db.json
```

## Voice Commands

### Enrollment Commands
- **"enroll me"** / **"add my voice"** / **"remember my voice"** / **"learn my voice"**
  - Starts the voice enrollment process
  - KLoROS will ask for your name, then spelling verification
  - You'll be prompted to repeat 5 enrollment sentences

### Management Commands
- **"list users"** / **"who do you know"**
  - Lists all enrolled users

- **"delete user [name]"** / **"remove user [name]"**
  - Removes a user's voice profile
  - Example: "delete user alice"

### Enrollment Flow Commands
- **"cancel"** / **"stop"** / **"quit"**
  - Cancels the current enrollment process

## Enrollment Process

1. **Start Enrollment**: Say "enroll me"
2. **Provide Name**: KLoROS asks for your name, speak it clearly
3. **Spell Name**: Spell your name letter by letter (e.g., "A-L-I-C-E")
4. **Record Sentences**: Repeat each of the 5 enrollment sentences when prompted:
   - "My name is [your name] and I need your help"
   - "KLoROS, please remember my voice clearly"
   - "I trust you to keep my secrets safe"
   - "What fragile crisis needs fixing today?"
   - "Thank you for being my digital companion"
5. **Completion**: KLoROS confirms enrollment success

## How It Works

1. **Wake Word Detection**: User says "KLoROS"
2. **Audio Capture**: System records the following voice command
3. **Speaker Identification**: If enabled, the system identifies the speaker from the audio
4. **Command Processing**: The identified user ID is used for personalized responses
5. **Response Generation**: KLoROS responds with knowledge of who is speaking

## Backend Types

### Mock Backend (`mock`)
- **Purpose**: Testing and development
- **Features**:
  - Pre-populated with test users (alice, bob, charlie)
  - Deterministic behavior based on audio content
  - Instant enrollment and identification
  - Special testing modes available

### Embedding Backend (`embedding`)
- **Purpose**: Production use
- **Features**:
  - Uses sentence-transformers for audio-to-text embedding conversion
  - Persistent JSON database storage
  - Cosine similarity matching
  - Configurable recognition thresholds

## File Structure

```
src/speaker/
├── __init__.py           # Package exports
├── base.py              # Core protocols and interfaces
├── mock_backend.py      # Mock backend for testing
├── embedding_backend.py # Production embedding backend
└── enrollment.py        # Name verification and enrollment sentences
```

## Testing

Run the comprehensive test suite:

```bash
python test_speaker_system.py
```

This tests:
- Speaker backend functionality
- Enrollment utilities (name parsing, verification)
- KLoROS integration
- Speaker identification flow

## Integration with Main Voice Loop

The speaker recognition system is seamlessly integrated into the main KLoROS voice loop:

1. **Initialization**: Speaker backend is initialized based on configuration
2. **Voice Processing**: After wake word detection and audio capture, speaker identification runs automatically
3. **User Context**: The identified user ID becomes the `operator_id` for that interaction
4. **Command Handling**: Enrollment commands are processed before LLM interaction
5. **Logging**: All speaker events are logged for debugging and analysis

## Troubleshooting

### Speaker Recognition Not Working
- Check that `KLR_ENABLE_SPEAKER_ID=1` is set
- Verify the speaker backend is available (`mock` should always work)
- Look for initialization messages in the console logs

### Enrollment Issues
- Ensure you're speaking clearly during enrollment
- Check that the microphone is working properly
- Try the enrollment process again if it fails

### Identification Problems
- Verify users are properly enrolled
- Check the recognition threshold setting
- Use "list users" to see enrolled speakers

### Mock Backend for Development
- Use `KLR_SPEAKER_BACKEND=mock` for reliable testing
- Mock backend has pre-populated test users
- Recognition behavior is deterministic for consistent testing

## Future Enhancements

Potential improvements for the speaker recognition system:

1. **Real Audio Embeddings**: Integration with dedicated audio embedding models
2. **Voice Activity Detection**: Better audio segmentation for enrollment
3. **Multi-user Conversations**: Support for multiple speakers in one session
4. **Voice Characteristics**: Age, gender, accent recognition
5. **Security Features**: Voice anti-spoofing measures
6. **Cloud Integration**: Remote speaker recognition services

## Privacy and Security

- Voice embeddings are stored locally by default
- No raw audio is persisted (only embeddings)
- User data can be deleted via voice commands
- All operations are logged for transparency