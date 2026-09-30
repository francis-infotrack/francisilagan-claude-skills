def area(w, h):
    return w * h


def kind(n):
    if n < 0:
        return "neg"
    if n == 0:
        return "zero"
    return "pos"
