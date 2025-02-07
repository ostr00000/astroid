# Licensed under the LGPL: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html
# For details: https://github.com/PyCQA/astroid/blob/main/LICENSE
# Copyright (c) https://github.com/PyCQA/astroid/blob/main/CONTRIBUTORS.txt

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, List, Optional, Tuple, TypeVar, Union, cast, overload

from astroid.context import _invalidate_cache
from astroid.typing import SuccessfulInferenceResult

if TYPE_CHECKING:
    from astroid import nodes

    _SuccessfulInferenceResultT = TypeVar(
        "_SuccessfulInferenceResultT", bound=SuccessfulInferenceResult
    )
    _Transform = Callable[
        [_SuccessfulInferenceResultT], Optional[SuccessfulInferenceResult]
    ]
    _Predicate = Optional[Callable[[_SuccessfulInferenceResultT], bool]]

_Vistables = Union[
    "nodes.NodeNG", List["nodes.NodeNG"], Tuple["nodes.NodeNG", ...], str, None
]
_VisitReturns = Union[
    SuccessfulInferenceResult,
    List[SuccessfulInferenceResult],
    Tuple[SuccessfulInferenceResult, ...],
    str,
    None,
]


class TransformVisitor:
    """A visitor for handling transforms.

    The standard approach of using it is to call
    :meth:`~visit` with an *astroid* module and the class
    will take care of the rest, walking the tree and running the
    transforms for each encountered node.

    Based on its usage in AstroidManager.brain, it should not be reinstantiated.
    """

    def __init__(self) -> None:
        # The typing here is incorrect, but it's the best we can do
        # Refer to register_transform and unregister_transform for the correct types
        self.transforms: defaultdict[
            type[SuccessfulInferenceResult],
            list[
                tuple[
                    _Transform[SuccessfulInferenceResult],
                    _Predicate[SuccessfulInferenceResult],
                ]
            ],
        ] = defaultdict(list)

    def _transform(self, node: SuccessfulInferenceResult) -> SuccessfulInferenceResult:
        """Call matching transforms for the given node if any and return the
        transformed node.
        """
        cls = node.__class__

        for transform_func, predicate in self.transforms[cls]:
            if predicate is None or predicate(node):
                ret = transform_func(node)
                # if the transformation function returns something, it's
                # expected to be a replacement for the node
                if ret is not None:
                    _invalidate_cache()
                    node = ret
                if ret.__class__ != cls:
                    # Can no longer apply the rest of the transforms.
                    break
        return node

    def _visit(self, node: nodes.NodeNG) -> SuccessfulInferenceResult:
        for name in node._astroid_fields:
            value = getattr(node, name)
            value = cast(_Vistables, value)
            visited = self._visit_generic(value)
            if visited != value:
                setattr(node, name, visited)
        return self._transform(node)

    @overload
    def _visit_generic(self, node: None) -> None:
        ...

    @overload
    def _visit_generic(self, node: str) -> str:
        ...

    @overload
    def _visit_generic(
        self, node: list[nodes.NodeNG]
    ) -> list[SuccessfulInferenceResult]:
        ...

    @overload
    def _visit_generic(
        self, node: tuple[nodes.NodeNG, ...]
    ) -> tuple[SuccessfulInferenceResult, ...]:
        ...

    @overload
    def _visit_generic(self, node: nodes.NodeNG) -> SuccessfulInferenceResult:
        ...

    def _visit_generic(self, node: _Vistables) -> _VisitReturns:
        if isinstance(node, list):
            return [self._visit_generic(child) for child in node]
        if isinstance(node, tuple):
            return tuple(self._visit_generic(child) for child in node)
        if not node or isinstance(node, str):
            return node

        return self._visit(node)

    def register_transform(
        self,
        node_class: type[_SuccessfulInferenceResultT],
        transform: _Transform[_SuccessfulInferenceResultT],
        predicate: _Predicate[_SuccessfulInferenceResultT] | None = None,
    ) -> None:
        """Register `transform(node)` function to be applied on the given node.

        The transform will only be applied if `predicate` is None or returns true
        when called with the node as argument.

        The transform function may return a value which is then used to
        substitute the original node in the tree.
        """
        self.transforms[node_class].append((transform, predicate))  # type: ignore[index, arg-type]

    def unregister_transform(
        self,
        node_class: type[_SuccessfulInferenceResultT],
        transform: _Transform[_SuccessfulInferenceResultT],
        predicate: _Predicate[_SuccessfulInferenceResultT] | None = None,
    ) -> None:
        """Unregister the given transform."""
        self.transforms[node_class].remove((transform, predicate))  # type: ignore[index, arg-type]

    def visit(self, module: nodes.Module) -> SuccessfulInferenceResult:
        """Walk the given astroid *tree* and transform each encountered node.

        Only the nodes which have transforms registered will actually
        be replaced or changed.
        """
        return self._visit(module)
