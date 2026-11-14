"""Public codes on records, and the registry of every code ever issued.

A model whose records have a public identity (a player, club, event,
organizer, or match) inherits ``PublicCodeModel`` and sets
``public_code_type``. See ADR 0008.
"""

from collections.abc import Collection, Iterable
from typing import Any, ClassVar, NoReturn, Self

from django.db import IntegrityError, models, router, transaction
from django.utils import timezone

from apps.public_ids import codes
from apps.public_ids.codes import CodeType

# Attempts to find an unused code before giving up. One collision is rare
# (see ADR 0008), so five in a row means something is wrong.
MAX_ATTEMPTS = 5


class IssuedCodeImmutable(RuntimeError):
    """Raised when code tries to change or delete an IssuedCode."""


class PublicCodeExhausted(RuntimeError):
    """Raised when every attempt to issue a new code collided."""


_IMMUTABLE_MESSAGE = "Issued codes are permanent: they cannot be changed or deleted."


class IssuedCodeQuerySet(models.QuerySet["IssuedCode"]):
    """Refuses bulk changes and deletes before any SQL runs."""

    def update(self, **kwargs: Any) -> NoReturn:
        raise IssuedCodeImmutable(_IMMUTABLE_MESSAGE)

    def delete(self) -> NoReturn:
        raise IssuedCodeImmutable(_IMMUTABLE_MESSAGE)

    def bulk_update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise IssuedCodeImmutable(_IMMUTABLE_MESSAGE)

    def bulk_create(
        self,
        objs: Iterable["IssuedCode"],
        batch_size: int | None = None,
        ignore_conflicts: bool = False,
        update_conflicts: bool = False,
        update_fields: Collection[str] | None = None,
        unique_fields: Collection[str] | None = None,
    ) -> list["IssuedCode"]:
        # An upsert would update an existing row.
        if update_conflicts:
            raise IssuedCodeImmutable(_IMMUTABLE_MESSAGE)
        return super().bulk_create(
            objs,
            batch_size=batch_size,
            ignore_conflicts=ignore_conflicts,
            update_fields=update_fields,
            unique_fields=unique_fields,
        )


class IssuedCode(models.Model):
    """One code that has been issued. The row stays when its record goes.

    The prefix names the record type, so there is no link to the record.
    The ORM refuses to change or delete a row. There is no database
    trigger: raw SQL can still delete rows (see ADR 0008).
    """

    code = models.CharField(max_length=32, unique=True, editable=False)
    issued_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = IssuedCodeQuerySet.as_manager()

    class Meta:
        verbose_name = "issued code"
        # Django's internal queries use the base manager, so it must be
        # the guarded one too.
        base_manager_name = "objects"

    def __str__(self) -> str:
        return self.code

    def save_base(
        self,
        raw: bool = False,
        force_insert: bool | tuple[models.base.ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        if (
            force_update
            or update_fields is not None
            or not self._state.adding
            or self.pk is not None
        ):
            raise IssuedCodeImmutable(_IMMUTABLE_MESSAGE)
        super().save_base(
            raw=raw,
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise IssuedCodeImmutable(_IMMUTABLE_MESSAGE)


def _generate(code_type: CodeType) -> str:
    """Generate a code. A separate function so tests can force collisions."""
    return codes.generate(code_type)


def _issue_code(code_type: CodeType, using: str) -> str:
    """Record and return a code that has never been issued."""
    for _ in range(MAX_ATTEMPTS):
        code = _generate(code_type)
        try:
            # A savepoint, so a collision leaves the caller's transaction usable.
            with transaction.atomic(using=using):
                IssuedCode.objects.using(using).create(code=code)
        except IntegrityError:
            continue
        return code
    raise PublicCodeExhausted(
        f"No unused {code_type.name.lower()} code after {MAX_ATTEMPTS} attempts."
    )


# Marks a loaded record whose public_code was deferred.
_NOT_LOADED = object()


class PublicCodeModel(models.Model):
    """A record with a public code, issued once on create and never changed.

    Concrete subclasses set ``public_code_type``. Create records through
    ``save()`` or ``objects.create()``: ``bulk_create``, ``QuerySet.update``,
    and raw SQL skip code generation and the no-change rule. ``bulk_create``
    without a code fails, since the column is NOT NULL.
    """

    public_code_type: ClassVar[CodeType]

    # default=None with null=False: a write that skips save() fails
    # instead of storing an empty code.
    public_code = models.CharField(
        max_length=32, unique=True, editable=False, default=None
    )

    _loaded_public_code: object

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if args:
            raise TypeError("Pass save() options by keyword.")
        if not self._state.adding:
            self._refuse_code_change()
            super().save(**kwargs)
            return
        if self.public_code is not None:
            raise ValueError("A public code is only ever generated, never set.")
        # Always insert: a new instance carrying an existing pk must not
        # overwrite that row's code.
        kwargs["force_insert"] = kwargs.get("force_insert") or True
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            self.public_code = _issue_code(self.public_code_type, using)
            try:
                super().save(**kwargs)
            except BaseException:
                # A retry of this instance gets a fresh code. The registry
                # row rolls back with the transaction.
                self.public_code = None
                raise
        self._loaded_public_code = self.public_code

    @classmethod
    def from_db(
        cls,
        db: str | None,
        field_names: Collection[str],
        values: Collection[Any],
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        instance = super().from_db(db, field_names, values, *args, **kwargs)
        # Remember the loaded code, so save() can refuse a changed one.
        instance._loaded_public_code = instance.__dict__.get("public_code", _NOT_LOADED)
        return instance

    def _refuse_code_change(self) -> None:
        if "public_code" not in self.__dict__:
            # Deferred and never touched: save() does not write it.
            return
        loaded = getattr(self, "_loaded_public_code", _NOT_LOADED)
        if loaded is _NOT_LOADED:
            loaded = (
                type(self)
                ._base_manager.using(self._state.db)
                .filter(pk=self.pk)
                .values_list("public_code", flat=True)
                .first()
            )
        if self.public_code != loaded:
            raise ValueError("A public code never changes once issued.")
