"""Market data MCP client."""

import argparse


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

    from client.agent import run

    try:
        answer = run(args.server, args.prompt, model=args.model or "")
    except ConnectionError as exc:
        parser.exit(1, f"kite-mcp-client: error: {exc}\n")
    print(answer)


if __name__ == "__main__":
    main()
