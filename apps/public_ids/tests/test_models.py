"""PublicCodeModel issues each record a code once, and IssuedCode keeps it."""

from collections.abc import Iterator

import pytest
from django.db import IntegrityError, connection, transaction

from apps.public_ids import codes
from apps.public_ids.codes import ALPHABET, CodeType
from apps.public_ids.models import (
    MAX_ATTEMPTS,
    IssuedCode,
    IssuedCodeImmutable,
    PublicCodeExhausted,
    PublicCodeModel,
)

pytestmark = pytest.mark.django_db

Thing = type[PublicCodeModel]


def _fixed_codes(
    monkeypatch: pytest.MonkeyPatch, sequence: list[str]
) -> list[CodeType]:
    """Make generation return ``sequence`` in order. Returns the call log."""
    calls: list[CodeType] = []
    remaining: Iterator[str] = iter(sequence)

    def fake_generate(code_type: CodeType) -> str:
        calls.append(code_type)
        return next(remaining)

    monkeypatch.setattr("apps.public_ids.models._generate", fake_generate)
    return calls


def _body_number(code: str) -> int:
    """The random part of a code as an integer (prefix and check dropped)."""
    body = code.replace("-", "")[1:-1]
    number = 0
    for char in body:
        number = number * 32 + ALPHABET.index(char)
    return number


def test_create_sets_a_canonical_code(thing_model: Thing) -> None:
    thing = thing_model._default_manager.create(label="made-up one")

    assert codes.normalize(thing.public_code, CodeType.PLAYER) == thing.public_code
    stored = thing_model._default_manager.get(pk=thing.pk)
    assert stored.public_code == thing.public_code
    assert IssuedCode.objects.filter(code=thing.public_code).exists()


def test_save_sets_a_code(thing_model: Thing) -> None:
    thing = thing_model(label="made-up one")
    assert thing.public_code is None

    thing.save()

    assert thing.public_code.startswith("P-")


def test_public_code_has_a_unique_constraint(thing_model: Thing) -> None:
    table = thing_model._meta.db_table
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table)

    unique_on_code = [
        name
        for name, details in constraints.items()
        if details["unique"] and details["columns"] == ["public_code"]
    ]
    assert len(unique_on_code) == 1


def test_issued_code_has_a_unique_constraint() -> None:
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, IssuedCode._meta.db_table
        )

    assert any(
        details["unique"] and details["columns"] == ["code"]
        for details in constraints.values()
    )


def test_consecutive_records_get_unrelated_codes(thing_model: Thing) -> None:
    first = thing_model._default_manager.create(label="made-up one")
    second = thing_model._default_manager.create(label="made-up two")

    assert first.public_code != second.public_code
    difference = abs(_body_number(first.public_code) - _body_number(second.public_code))
    assert difference > 1


def test_codes_do_not_follow_row_ids(thing_model: Thing) -> None:
    things = [
        thing_model._default_manager.create(label=f"made-up {n}") for n in range(20)
    ]

    numbers = [_body_number(thing.public_code) for thing in things]
    assert numbers != sorted(numbers)
    assert len(set(numbers)) == 20


def test_a_forced_collision_is_retried(
    thing_model: Thing, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = codes.generate(CodeType.PLAYER)
    fresh = codes.generate(CodeType.PLAYER)
    IssuedCode.objects.create(code=taken)
    calls = _fixed_codes(monkeypatch, [taken, fresh])

    thing = thing_model._default_manager.create(label="made-up one")

    assert thing.public_code == fresh
    assert calls == [CodeType.PLAYER, CodeType.PLAYER]
    assert set(IssuedCode.objects.values_list("code", flat=True)) == {taken, fresh}


def test_a_collision_with_a_live_record_is_retried(
    thing_model: Thing, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = thing_model._default_manager.create(label="made-up one")
    fresh = codes.generate(CodeType.PLAYER)
    _fixed_codes(monkeypatch, [existing.public_code, fresh])

    thing = thing_model._default_manager.create(label="made-up two")

    assert thing.public_code == fresh


def test_every_attempt_colliding_raises(
    thing_model: Thing, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = codes.generate(CodeType.PLAYER)
    IssuedCode.objects.create(code=taken)
    calls = _fixed_codes(monkeypatch, [taken] * MAX_ATTEMPTS)
    thing = thing_model(label="made-up one")

    with pytest.raises(PublicCodeExhausted):
        thing.save()

    assert MAX_ATTEMPTS == 5
    assert len(calls) == MAX_ATTEMPTS
    assert thing.public_code is None
    assert thing_model._default_manager.count() == 0
    assert IssuedCode.objects.count() == 1


def test_public_code_exhausted_is_a_runtime_error() -> None:
    assert issubclass(PublicCodeExhausted, RuntimeError)


def test_a_deleted_records_code_is_never_issued_again(
    thing_model: Thing, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = thing_model._default_manager.create(label="made-up one")
    old_code = old.public_code
    old.delete()
    assert IssuedCode.objects.filter(code=old_code).exists()
    fresh = codes.generate(CodeType.PLAYER)
    _fixed_codes(monkeypatch, [old_code, fresh])

    thing = thing_model._default_manager.create(label="made-up two")

    assert thing.public_code == fresh


def test_a_failed_insert_rolls_back_its_code(thing_model: Thing) -> None:
    thing_model._default_manager.create(label="made-up one")
    duplicate = thing_model(label="made-up one")

    with pytest.raises(IntegrityError):
        duplicate.save()

    assert duplicate.public_code is None
    assert IssuedCode.objects.count() == 1


def test_a_retried_save_gets_a_fresh_code(thing_model: Thing) -> None:
    thing_model._default_manager.create(label="made-up one")
    thing = thing_model(label="made-up one")
    with pytest.raises(IntegrityError):
        thing.save()
    thing.label = "made-up two"  # type: ignore[attr-defined]

    thing.save()

    assert thing.public_code is not None
    assert IssuedCode.objects.count() == 2


def test_changing_the_code_of_a_saved_record_raises(thing_model: Thing) -> None:
    thing = thing_model._default_manager.create(label="made-up one")
    original = thing.public_code
    thing.public_code = codes.generate(CodeType.PLAYER)

    with pytest.raises(ValueError, match="never changes"):
        thing.save()

    assert thing_model._default_manager.get(pk=thing.pk).public_code == original


def test_changing_the_code_of_a_loaded_record_raises(thing_model: Thing) -> None:
    created = thing_model._default_manager.create(label="made-up one")
    loaded = thing_model._default_manager.get(pk=created.pk)
    loaded.public_code = codes.generate(CodeType.PLAYER)

    with pytest.raises(ValueError, match="never changes"):
        loaded.save(update_fields=["public_code"])

    stored = thing_model._default_manager.get(pk=created.pk)
    assert stored.public_code == created.public_code


def test_changing_a_deferred_code_raises(thing_model: Thing) -> None:
    created = thing_model._default_manager.create(label="made-up one")
    loaded = thing_model._default_manager.only("pk").get(pk=created.pk)
    loaded.public_code = codes.generate(CodeType.PLAYER)

    with pytest.raises(ValueError, match="never changes"):
        loaded.save()

    stored = thing_model._default_manager.get(pk=created.pk)
    assert stored.public_code == created.public_code


def test_saving_a_loaded_record_keeps_its_code(thing_model: Thing) -> None:
    created = thing_model._default_manager.create(label="made-up one")
    loaded = thing_model._default_manager.get(pk=created.pk)
    loaded.label = "made-up two"  # type: ignore[attr-defined]

    loaded.save()

    stored = thing_model._default_manager.get(pk=created.pk)
    assert stored.public_code == created.public_code
    assert stored.label == "made-up two"  # type: ignore[attr-defined]


def test_reading_a_deferred_code_then_saving_is_allowed(thing_model: Thing) -> None:
    created = thing_model._default_manager.create(label="made-up one")
    loaded = thing_model._default_manager.only("pk").get(pk=created.pk)
    assert loaded.public_code == created.public_code

    loaded.save()

    stored = thing_model._default_manager.get(pk=created.pk)
    assert stored.public_code == created.public_code


def test_saving_a_deferred_record_keeps_its_code(thing_model: Thing) -> None:
    created = thing_model._default_manager.create(label="made-up one")
    loaded = thing_model._default_manager.only("pk", "label").get(pk=created.pk)
    loaded.label = "made-up two"  # type: ignore[attr-defined]

    loaded.save()

    stored = thing_model._default_manager.get(pk=created.pk)
    assert stored.public_code == created.public_code


def test_a_new_instance_never_overwrites_an_existing_row(thing_model: Thing) -> None:
    created = thing_model._default_manager.create(label="made-up one")
    impostor = thing_model(pk=created.pk, label="made-up two")

    with pytest.raises(IntegrityError):
        impostor.save()

    stored = thing_model._default_manager.get(pk=created.pk)
    assert stored.public_code == created.public_code
    assert stored.label == "made-up one"  # type: ignore[attr-defined]


def test_save_refuses_positional_options(thing_model: Thing) -> None:
    thing = thing_model(label="made-up one")

    with pytest.raises(TypeError):
        thing.save(False)

    assert thing_model._default_manager.count() == 0


def test_presetting_a_code_on_create_raises(thing_model: Thing) -> None:
    chosen = codes.generate(CodeType.PLAYER)

    with pytest.raises(ValueError, match="generated"):
        thing_model._default_manager.create(label="made-up one", public_code=chosen)

    assert thing_model._default_manager.count() == 0
    assert IssuedCode.objects.count() == 0


def test_bulk_create_without_a_code_fails(thing_model: Thing) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        thing_model._default_manager.bulk_create([thing_model(label="made-up one")])


# IssuedCode


@pytest.fixture
def issued() -> IssuedCode:
    return IssuedCode.objects.create(code=codes.generate(CodeType.CLUB))


def test_issued_code_str_is_the_code(issued: IssuedCode) -> None:
    assert str(issued) == issued.code
    assert issued.issued_at is not None


def test_issued_code_immutable_is_a_runtime_error() -> None:
    assert issubclass(IssuedCodeImmutable, RuntimeError)


def test_issued_code_save_on_existing_row_is_refused(issued: IssuedCode) -> None:
    original = issued.code
    issued.code = codes.generate(CodeType.CLUB)

    with pytest.raises(IssuedCodeImmutable):
        issued.save()

    assert IssuedCode.objects.get(pk=issued.pk).code == original


def test_issued_code_force_update_is_refused(issued: IssuedCode) -> None:
    fresh = IssuedCode(pk=issued.pk, code=codes.generate(CodeType.CLUB))

    with pytest.raises(IssuedCodeImmutable):
        fresh.save(force_update=True)

    assert IssuedCode.objects.get(pk=issued.pk).code == issued.code


def test_issued_code_instance_delete_is_refused(issued: IssuedCode) -> None:
    with pytest.raises(IssuedCodeImmutable):
        issued.delete()

    assert IssuedCode.objects.filter(pk=issued.pk).exists()


def test_issued_code_queryset_update_is_refused(issued: IssuedCode) -> None:
    with pytest.raises(IssuedCodeImmutable):
        IssuedCode.objects.update(code="P-0000-000A")

    assert IssuedCode.objects.get(pk=issued.pk).code == issued.code


def test_issued_code_queryset_delete_is_refused(issued: IssuedCode) -> None:
    with pytest.raises(IssuedCodeImmutable):
        IssuedCode.objects.all().delete()

    assert IssuedCode.objects.count() == 1


def test_issued_code_bulk_update_is_refused(issued: IssuedCode) -> None:
    issued.code = codes.generate(CodeType.CLUB)

    with pytest.raises(IssuedCodeImmutable):
        IssuedCode.objects.bulk_update([issued], ["code"])


def test_issued_code_upsert_is_refused(issued: IssuedCode) -> None:
    with pytest.raises(IssuedCodeImmutable):
        IssuedCode.objects.bulk_create(
            [IssuedCode(code=issued.code)],
            update_conflicts=True,
            update_fields=["issued_at"],
            unique_fields=["code"],
        )


def test_issued_code_bulk_create_inserts(issued: IssuedCode) -> None:
    IssuedCode.objects.bulk_create([IssuedCode(code=codes.generate(CodeType.EVENT))])

    assert IssuedCode.objects.count() == 2


def test_issued_code_duplicate_insert_fails(issued: IssuedCode) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        IssuedCode.objects.create(code=issued.code)


def test_a_caller_force_insert_tuple_is_kept(thing_model: Thing) -> None:
    thing = thing_model(label="made-up one")

    thing.save(force_insert=(thing_model,))

    assert (
        thing_model._default_manager.get(pk=thing.pk).public_code == thing.public_code
    )


def test_a_caller_force_insert_tuple_must_name_a_base(thing_model: Thing) -> None:
    thing = thing_model(label="made-up one")

    with pytest.raises(TypeError):
        thing.save(force_insert=(IssuedCode,))

    assert thing.public_code is None
    assert thing_model._default_manager.count() == 0
