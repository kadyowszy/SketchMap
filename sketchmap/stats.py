import time
from contextlib import contextmanager
from .config import PIPELINE_BUDGET_S


class Stats:
    def __init__(self):
        self.sections, self.order, self.timings = {}, [], {}

    def add(self, section, text):
        if section not in self.sections:
            self.sections[section] = []
            self.order.append(section)
        self.sections[section].append(text)

    def reset(self, section):
        self.sections[section] = []
        if section not in self.order:
            self.order.append(section)

    def block(self, section, title, formula=None, compute=None, result=None, visual=None):
        def L(x):
            return [] if x is None else ([x] if isinstance(x, str) else list(x))
        self.add(section, f"[{title}]")
        for tag, body in (("FORMULA", formula), ("COMPUTATION", compute), ("RESULT", result), ("VISUAL EFFECT", visual)):
            b = L(body)
            if b:
                self.add(section, f"  {tag}")
                for line in b:
                    self.add(section, "    " + line)
        self.add(section, "")

    @contextmanager
    def timer(self, name):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.timings[name] = (time.perf_counter() - t) * 1000

    def total_ms(self):
        return sum(self.timings.values())

    def names(self):
        return ["All", "Timing"] + self.order + ["Manual editing"]

    def render(self, extra=None, only=None):
        show = lambda name: only in (None, "All", name)
        out = []
        if show("Timing"):
            out.append("=" * 78)
            out.append("TIMING")
            out.append("=" * 78)
            for k, v in self.timings.items():
                out.append(f"  {k:<24}{v:9.1f} ms")
            out.append(f"  {'TOTAL':<24}{self.total_ms():9.1f} ms   (budget: {PIPELINE_BUDGET_S*1000:.0f} ms)")
            out.append("")
        for s in self.order:
            if show(s):
                out += ["=" * 78, s.upper(), "=" * 78]
                out += self.sections[s]
        if extra and show("Manual editing"):
            out += extra
        return "\n".join(out)
