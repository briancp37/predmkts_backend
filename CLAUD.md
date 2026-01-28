
## FORBRIAN.md Files

For every sprint, write a detailed FORBRIAN.md file that explains the whole sprint in plain language located at `./plans/releases/$release/sprints/$sprint/FORBRIAN.md`.

Explain the technical architecture, the structure of the codebase and how the various parts are connected, the technologies used, why we made these technical decisions, and lessons I can learn from it (this shuld include the bufs we ran into and how we fixed them, potential pitfals and how to avoid them in teh future, new technologies used, how good engineers think and work, best practices, etc).

It should be very engaging to read; dont make it sound like boring technical documentation/textbook.  Where appropriate, use analogies and anecdotes to make it more understandable and memorable.

Always use `uv` when possible.

You can add rate limits to here for the external APIs.

## Kalshi API Rate Limits

**Tiers:**

| Tier | Read | Write |
|------|------|-------|
| Basic | 20/sec | 10/sec |
| Advanced | 30/sec | 30/sec |
| Premier | 100/sec | 100/sec |
| Prime | 400/sec | 400/sec |

- **Basic**: Default after signup
- **Advanced**: Complete the Advanced API form
- **Premier/Prime**: Monthly volume thresholds (3.75% / 7.5%) + technical competency

**Write-limited endpoints:**
- CreateOrder
- CancelOrder
- AmendOrder
- DecreaseOrder
- BatchCreateOrders (each item = 1 transaction)
- BatchCancelOrders (each cancellation = 0.2 transactions)

Kalshi reserves the right to downgrade tiers for inactivity.