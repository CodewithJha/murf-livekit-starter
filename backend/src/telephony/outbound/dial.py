"""Trigger a Dukaan Dost outbound order-confirmation call.

Make sure the outbound worker is running first:

    uv run python src/telephony/outbound/agent.py start

Then place a call (Linphone username or E.164 phone):

    uv run python src/telephony/outbound/dial.py \\
        --to codewithjha \\
        --name Priyanshu \\
        --order "two litres milk and one kilo onion"

Full SIP URIs are auto-normalized to the username for LiveKit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = Path(__file__).resolve().parents[2]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

load_dotenv(_BACKEND_ROOT / ".env.local")
load_dotenv(".env.local")

from livekit import api  # noqa: E402

from telephony.outbound.call_context import normalize_sip_call_to  # noqa: E402

AGENT_NAME = "outbound-agent"


async def dial(
    phone_number: str,
    room_name: str,
    *,
    customer_name: str,
    order_summary: str,
    locale: str,
) -> None:
    """Create the room and dispatch the outbound agent into it."""
    metadata = {
        "phone_number": phone_number,
        "customer_name": customer_name,
        "order_summary": order_summary,
        "locale": locale,
    }
    lk = api.LiveKitAPI()
    try:
        await lk.room.create_room(api.CreateRoomRequest(name=room_name))
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=json.dumps(metadata, ensure_ascii=False),
            )
        )
    finally:
        await lk.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Place a Dukaan Dost outbound order-confirmation call."
    )
    parser.add_argument(
        "--to",
        required=True,
        help=(
            "Destination: Linphone username (codewithjha), full SIP URI, "
            "or E.164 phone (+91…)."
        ),
    )
    parser.add_argument(
        "--name",
        default=os.getenv("OUTBOUND_CUSTOMER_NAME", "Priyanshu"),
        help="Customer name for the greeting and memory lookup.",
    )
    parser.add_argument(
        "--order",
        default=os.getenv(
            "OUTBOUND_ORDER_SUMMARY",
            "two litres milk and one kilo onion",
        ),
        help="Order summary to confirm on the call.",
    )
    parser.add_argument(
        "--locale",
        default=os.getenv("OUTBOUND_LOCALE", "en-IN"),
        choices=["en-IN", "hi-IN"],
        help="Spoken language for greeting and replies.",
    )
    parser.add_argument(
        "--room",
        default=None,
        help="Room name. Defaults to a generated outbound-* name.",
    )
    args = parser.parse_args()

    target = normalize_sip_call_to((args.to or "").strip())
    if not target:
        sys.exit("--to is required")

    room_name = args.room or f"outbound-{uuid.uuid4().hex[:8]}"

    asyncio.run(
        dial(
            target,
            room_name,
            customer_name=(args.name or "").strip(),
            order_summary=(args.order or "").strip() or "your grocery order",
            locale=args.locale,
        )
    )

    print(f"Dispatched {AGENT_NAME} to room '{room_name}' to call {target}.")
    if args.to.strip() != target:
        print(f"(normalized from {args.to!r})")
    print(f"Customer={args.name!r} order={args.order!r} locale={args.locale}")
    print("Watch the outbound worker terminal for call progress.")


if __name__ == "__main__":
    main()
