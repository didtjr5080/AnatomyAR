class VictoryCountdown:
    def __init__(self):
        self.wait_release=False
        self.clear()

    def clear(self):
        self.target=self.since=self.last=self.number=self.received=self.started=None

    def resume(self):
        self.clear()
        self.wait_release=True

    def update(self,hands,timestamp,now,max_age):
        if self.started is not None: return self.advance(now)
        if timestamp is None or not 0<=now-timestamp<=max_age:
            self.clear()
            return False
        if self.last is not None and timestamp<=self.last: return False
        if self.last is not None and timestamp-self.last>max_age: self.clear()
        self.last=timestamp
        self.received=now
        if not hands:
            self.clear()
            self.wait_release=False
            return False
        if self.wait_release: return False
        target=self.target if self.target in hands else sorted(hands)[0]
        if target!=self.target:
            self.target,self.since=target,timestamp
        elapsed=timestamp-self.since
        if elapsed>=500:
            self.started=now
            self.number=3
        return False

    def advance(self,now):
        if self.started is None: return False
        elapsed=max(0,now-self.started)
        self.number=max(1,3-elapsed//1000)
        if elapsed>=3000:
            self.resume()
            return True
        return False
