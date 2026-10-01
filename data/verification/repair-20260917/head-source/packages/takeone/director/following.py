"""Replace these two placeholder hooks when the external follow code arrives.

The Director only selects and prepares intent. `start_following` belongs at the
future supervised runtime start boundary, never in preview compilation. Hooks
currently return pending and perform no IO, so a no-op cannot masquerade as live
tracking. The external runtime must own fresh identity, loss handling and stop.
"""


def start_cart_follow(*, actor_id, on_loss):
    """TODO: connect the friend's cart-follow controller at runtime start."""
    return dict(
        controller="cart_follow",
        actor_id=actor_id,
        on_loss=on_loss,
        active=False,
        state="implementation_pending",
    )


def start_head_follow(*, actor_id, on_loss, aim_offset_m):
    """TODO: connect head tracking; apply this framing offset relative to the head."""
    return dict(
        controller="head_follow",
        actor_id=actor_id,
        on_loss=on_loss,
        aim_offset_m=list(aim_offset_m),
        active=False,
        state="implementation_pending",
    )


def start_following(request):
    """Dispatch only the selected hooks. Calling this today activates no devices."""
    results = []
    if request["cart"] == "follow_actor":
        results.append(start_cart_follow(actor_id=request["actor_id"], on_loss=request["on_loss"]))
    if request["phone"] == "follow_head":
        results.append(
            start_head_follow(
                actor_id=request["actor_id"],
                on_loss=request["on_loss"],
                aim_offset_m=request.get("aim_offset_m", [0.0, 0.0, 0.0]),
            )
        )
    return dict(controllers=results, active=bool(results) and all(r["active"] for r in results))
