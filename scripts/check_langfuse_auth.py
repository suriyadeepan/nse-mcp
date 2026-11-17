"""Check Langfuse credentials and tracing with a small OpenAI completion."""

from dotenv import load_dotenv

load_dotenv()

# Load the environment before importing either SDK so both see .env settings.
from langfuse import get_client
from langfuse.openai import openai


def main() -> int:
    langfuse = get_client()

    try:
        if not langfuse.auth_check():
            print("Langfuse authentication failed.")
            return 1
    except Exception as exc:
        print(f"Langfuse authentication check failed ({type(exc).__name__}).")
        return 1

    print("Langfuse authentication succeeded.")
    try:
        completion = openai.chat.completions.create(
            name="test-chat",
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a very accurate calculator."},
                {"role": "user", "content": "1 + 1 = ?"},
            ],
            metadata={"someMetadataKey": "someValue"},
        )
        print(completion.choices[0].message.content)
        return 0
    except Exception as exc:
        print(f"OpenAI completion failed ({type(exc).__name__}).")
        return 1
    finally:
        langfuse.flush()


if __name__ == "__main__":
    raise SystemExit(main())
