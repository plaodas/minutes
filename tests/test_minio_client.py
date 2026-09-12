from minutes.minio_client import MinioService


class FakeObject:
    def __init__(self, chunks=None, *, read_error=None, close_error=None):
        self.chunks = list(chunks or [b"hello"])
        self.read_error = read_error
        self.close_error = close_error
        self.closed = False
        self.released = False

    def stream(self, chunk_size):
        del chunk_size
        yield from self.chunks

    def read(self):
        if self.read_error is not None:
            raise self.read_error
        return b"".join(self.chunks)

    def close(self):
        self.closed = True
        if self.close_error is not None:
            raise self.close_error

    def release_conn(self):
        self.released = True


class FakeClient:
    def __init__(self, obj):
        self.obj = obj
        self.gets = []

    def get_object(self, bucket, object_name):
        self.gets.append((bucket, object_name))
        return self.obj


def test_iter_object_opens_eagerly_and_closes_after_consume():
    obj = FakeObject(chunks=[b"a", b"", b"b"])
    client = FakeClient(obj)
    body = MinioService(client=client).iter_object("outputs", "minutes/a.txt")

    assert client.gets == [("outputs", "minutes/a.txt")]
    assert obj.closed is False
    assert list(body) == [b"a", b"b"]
    assert obj.closed is True
    assert obj.released is True


def test_iter_object_releases_when_iteration_stops_early():
    obj = FakeObject(chunks=[b"one", b"two"])
    body = MinioService(client=FakeClient(obj)).iter_object("b", "o")

    assert next(body) == b"one"
    body.close()
    assert obj.closed is True
    assert obj.released is True


def test_read_object_text_decodes_and_closes():
    obj = FakeObject(chunks=[b"minutes text"])
    text = MinioService(client=FakeClient(obj)).read_object_text("outputs", "a.txt")

    assert text == "minutes text"
    assert obj.closed is True
    assert obj.released is True


def test_read_object_text_closes_when_read_fails():
    obj = FakeObject(read_error=OSError("read failed"))
    service = MinioService(client=FakeClient(obj))

    try:
        service.read_object_text("outputs", "a.txt")
    except OSError:
        pass
    else:
        raise AssertionError("expected OSError")

    assert obj.closed is True
    assert obj.released is True


def test_release_object_still_releases_when_close_fails():
    obj = FakeObject(close_error=OSError("close failed"))
    MinioService(client=FakeClient(obj))._release_object(obj, "outputs", "a.txt")

    assert obj.closed is True
    assert obj.released is True
