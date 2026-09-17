"""Allow running the package as a module: python -m printful_mcp"""

import argparse
import os
import sys


def parse_args():
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Printful MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport type: stdio (default, for Cursor/Claude), http (for HTTP clients), sse (legacy)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind HTTP server (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP server (default: 8000)"
    )
    return parser.parse_args()


def main():
    """Entry point for the MCP server."""
    args = parse_args()

    # Import server module
    from .server import mcp

    # Check for API key
    if not os.getenv("PRINTFUL_API_KEY"):
        print("Error: PRINTFUL_API_KEY environment variable is required", file=sys.stderr)
        print("Get your API key from: https://www.printful.com/dashboard/api", file=sys.stderr)
        sys.exit(1)

    # Where the HTTP address goes is the second thing that moved between SDK
    # majors, and unlike the class rename it is invisible at import. mcp 1.x
    # carries host and port on `mcp.settings`. 2.x removed those fields -- the
    # assignment raises ValueError -- and takes them as run() keywords instead,
    # which 1.x in turn rejects, because its run() has no **kwargs.
    #
    # Feature-detect the attribute rather than sniffing a version string: the
    # attribute is the thing that actually differs, and it stays correct if a
    # future release moves the fields again.
    run_kwargs: dict = {}
    if args.transport in ("http", "sse"):
        print(
            f"Starting {args.transport.upper()} server on http://{args.host}:{args.port}",
            file=sys.stderr,
        )
        if hasattr(mcp.settings, "host"):  # mcp 1.x
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        else:  # mcp 2.x
            run_kwargs = {"host": args.host, "port": args.port}

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "http":
        mcp.run(transport="streamable-http", **run_kwargs)
    elif args.transport == "sse":
        mcp.run(transport="sse", **run_kwargs)


if __name__ == "__main__":
    main()
