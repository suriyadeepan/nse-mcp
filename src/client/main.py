"""Market data MCP client."""

import argparse


def _initialize_langfuse():
    """Load environment settings before creating the Langfuse client."""
    from dotenv import load_dotenv

    load_dotenv()

    from langfuse import get_client

    return get_client()


def main() -> None:
    parser = argparse.ArgumentParser(prog="kite-mcp-client")
    parser.add_argument(
        "--server",
        default="http://localhost:8000/mcp",
        help="Streamable HTTP endpoint of the market data MCP server",
    )
    parser.add_argument("--prompt", help="Query to send to the agent")
    parser.add_argument("--model", help="OpenAI model (defaults to OPENAI_MODEL or gpt-4o-mini)")
    args = parser.parse_args()

    if not args.prompt:
        parser.error("--prompt is required")

    langfuse = _initialize_langfuse()

    try:
        from client.agent import run

        answer = run(args.server, args.prompt, model=args.model or "")
    except ConnectionError as exc:
        from client.agent import _redact_secrets

        parser.exit(1, f"kite-mcp-client: error: {_redact_secrets(str(exc))}\n")
    finally:
        langfuse.flush()
    print(answer)


if __name__ == "__main__":
    main()
