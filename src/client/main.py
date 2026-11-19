"""Market data MCP client."""

import argparse
import os

from client.discovery import DEFAULT_SERVER_URL


def _resolve_server_config(server_override: str | None) -> tuple[str, str | None]:
    """Resolve the endpoint and optional bearer token from CLI and environment."""
    server_url = (
        server_override
        or os.environ.get("MCP_SERVER_URL")
        or DEFAULT_SERVER_URL
    )
    bearer_token = os.environ.get("MCP_BEARER_TOKEN")

    # Keep an unauthenticated localhost workflow for development. Configured
    # non-local endpoints require credentials before any network request.
    if server_url != DEFAULT_SERVER_URL and not bearer_token:
        raise ValueError("MCP_BEARER_TOKEN is required when using a remote MCP server.")
    return server_url, bearer_token


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
        default=None,
        help="Streamable HTTP endpoint of the market data MCP server",
    )
    parser.add_argument("--prompt", help="Query to send to the agent")
    parser.add_argument("--model", help="OpenAI model (defaults to OPENAI_MODEL or gpt-4o-mini)")
    args = parser.parse_args()

    if not args.prompt:
        parser.error("--prompt is required")

    langfuse = _initialize_langfuse()

    try:
        try:
            server_url, _bearer_token = _resolve_server_config(args.server)
        except ValueError as exc:
            parser.error(str(exc))
        from client.agent import run

        answer = run(server_url, args.prompt, model=args.model or "")
    except ConnectionError as exc:
        from client.agent import _redact_secrets

        parser.exit(1, f"kite-mcp-client: error: {_redact_secrets(str(exc))}\n")
    finally:
        langfuse.flush()
    print(answer)


if __name__ == "__main__":
    main()
