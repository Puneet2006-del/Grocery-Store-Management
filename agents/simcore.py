"""Small Monte Carlo engine shared by the agents.

Plays the coming days forward many times with random demand, selling oldest stock first.
Using the same random demand for 'do nothing' and for each option makes the comparison fair.
"""
import numpy as np

N_SIM = 2000


def draw_base_demand(mu, sd, days, n, rng):
    """Gamma-distributed daily demand, shape (days, n). The 7-day forecast repeats after day 7."""
    out = np.zeros((days, n))
    for d in range(days):
        m, s = mu[d % 7], sd[d % 7]
        if m > 0.05:
            out[d] = rng.gamma(min((m / s) ** 2, 1e4), s * s / m, n)
    return out


def fifo_run(qty, start, expire, demand):
    """qty, start, expire: one entry per batch. A batch can be sold from day `start` up to the day
    before `expire` (day 1 = tomorrow); leftovers are written off on day `expire`.

    Returns sold (days, n), unsold per batch (batches, n), shortfall (days, n).
    """
    days, n = demand.shape
    order = np.argsort(expire, kind="stable")
    rem = np.tile(np.asarray(qty, float)[order][:, None], (1, n))
    start, expire = np.asarray(start)[order], np.asarray(expire)[order]
    unsold = np.zeros_like(rem)
    sold, short = np.zeros((days, n)), np.zeros((days, n))
    for d in range(1, days + 1):
        for i in range(len(order)):
            if expire[i] == d:
                unsold[i] = rem[i]
                rem[i] = 0
        left = demand[d - 1].copy()
        for i in range(len(order)):
            if start[i] <= d < expire[i]:
                take = np.minimum(rem[i], left)
                rem[i] -= take
                left -= take
        sold[d - 1] = demand[d - 1] - left
        short[d - 1] = left
    back = np.empty_like(order)
    back[order] = np.arange(len(order))
    return sold, unsold[back], short


def profit(sold, unsold, price_per_day, cost):
    """Revenue minus the cost of every unit sold or written off."""
    revenue = (sold * np.asarray(price_per_day, float)[:, None]).sum(axis=0)
    return revenue - cost * (sold.sum(axis=0) + unsold.sum(axis=0))
