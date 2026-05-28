"""CLI pipeline runner for the home fix agent."""
from __future__ import annotations
import argparse
import logging
import sys

from src.agents import order_manager
from src.intake.photo import validate_and_store
from src.models.schemas import PipelineResult, PipelineStage
from src.pipeline import advance, start_session
from src.storage.store import list_sessions, load_result, save_result

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _print_result(result: PipelineResult):
    """Pretty-print pipeline result to terminal."""
    if result.error:
        print(f"\n❌ Error: {result.error}")
        return

    a = result.analysis
    if a:
        print(f"\n📋 Issue: {a.item_category} — {a.problem_type} (confidence: {a.confidence:.0%})")
        print(f"   {a.description}")
        if a.visible_text:
            print(f"   Visible text: {', '.join(a.visible_text)}")
        labels = {1: "Trivial", 2: "Easy", 3: "Moderate", 4: "Hard", 5: "Professional"}
        print(f"\n📊 Difficulty: {labels.get(a.difficulty_score, '?')} ({a.difficulty_score}/5)")
        if a.difficulty_summary:
            print(f"   {a.difficulty_summary}")
        if a.required_tools:
            print(f"   🔧 Tools: {', '.join(a.required_tools)}")
        if a.fix_summary:
            print(f"\n📝 Fix Plan:\n   {a.fix_summary}")
        if a.diy_or_hire:
            rec = {"diy": "🟢 DIY — you can do this yourself", "either": "🟡 Either — DIY if handy, or hire help", "hire": "🔴 Hire a handyman recommended"}
            print(f"\n💡 {rec.get(a.diy_or_hire, a.diy_or_hire)}")
            if a.hire_reason:
                print(f"   {a.hire_reason}")
            if a.diy_or_hire != "diy" and a.hire_price_min_cents > 0:
                print(f"   💰 Estimated labor: ${a.hire_price_min_cents // 100}–${a.hire_price_max_cents // 100} (not including parts)")

    s = result.spec
    if s:
        print(f"\n🔧 Specs: {s.search_query}")
        for k, v in s.attributes.items():
            conf = s.confidence_per_field.get(k, 0)
            print(f"   {k}: {v} ({conf:.0%})")

    if result.products:
        print(f"\n🛒 Top {len(result.products)} products:")
        for p in result.products:
            price = f"${p.price_cents / 100:.2f}"
            stars = f"⭐{p.rating}" if p.rating else ""
            print(f"   {p.rank}. {p.title}")
            print(f"      {price} | {stars} ({p.review_count} reviews) | Score: {p.match_score:.2f}")
            print(f"      {p.recommendation_reason}")
            if p.url:
                print(f"      {p.url}")


def cli_main():
    parser = argparse.ArgumentParser(description="Home Fix Agent")
    sub = parser.add_subparsers(dest="command")

    analyze_p = sub.add_parser("analyze", help="Analyze a photo and find products")
    analyze_p.add_argument("photo", help="Path to photo")
    analyze_p.add_argument("--description", "-d", default="", help="Optional description")

    sub.add_parser("history", help="List past sessions")

    replay_p = sub.add_parser("replay", help="Replay a past session")
    replay_p.add_argument("session_id", help="Session ID")

    sub.add_parser("web", help="Start web UI")

    args = parser.parse_args()

    if args.command == "analyze":
        # Validate and store photo first
        try:
            stored = validate_and_store(args.photo, "tmp")
        except (FileNotFoundError, ValueError) as e:
            print(f"\n❌ {e}")
            return

        result = start_session(stored, args.description)
        _print_result(result)

        if result.products:
            print(f"\n💾 Session: {result.session.session_id}")
            try:
                while True:
                    choice = input("\nSelect product (1-5), 'refine <criteria>', or 'q' to quit: ").strip()
                    if choice.lower() in ('q', 'quit', ''):
                        break
                    if choice.lower().startswith('refine '):
                        feedback = choice[7:].strip()
                        if feedback:
                            result = advance(result, feedback)
                            _print_result(result)
                            continue
                    if choice.isdigit() and 1 <= int(choice) <= len(result.products):
                        product = result.products[int(choice) - 1]
                        order = order_manager.create_order(result.session.session_id, product)
                        price = f"${order.total_price_cents / 100:.2f}"
                        print(f"\n📦 Order: {order.product_title}")
                        print(f"   Total: {price}")
                        confirm = input("   Place order? (yes/no): ").strip().lower()
                        if confirm in ("yes", "y"):
                            order = order_manager.confirm_order(order)
                            result.order = order
                            result.stage = PipelineStage.DONE
                            save_result(result)
                            print(f"   ✅ Order placed! ID: {order.retailer_order_id}")
                        else:
                            order = order_manager.cancel_order(order)
                            result.order = order
                            save_result(result)
                            print("   ❌ Order cancelled.")
                        break
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")

    elif args.command == "history":
        for s in list_sessions():
            print(f"  {s['session_id']}  {s.get('created_at', '')}  {s.get('category', '')}  {s.get('status', '')}")

    elif args.command == "replay":
        r = load_result(args.session_id)
        if r:
            _print_result(r)
        else:
            print(f"Session {args.session_id} not found.")

    elif args.command == "web":
        from src.web import start_server
        start_server()

    else:
        parser.print_help()


if __name__ == "__main__":
    cli_main()
