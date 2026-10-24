"""Reject storage/qualifiers that mathematical C frontends do not model."""
from pycparser import c_ast


def validate_automatic_locals(function,error_type=ValueError):
    def visit(node):
        if isinstance(node,c_ast.Decl):
            if node.storage or node.quals:raise error_type('Mathematical C frontends require unqualified automatic local declarations')
            current=node.type
            while current is not None:
                if getattr(current,'quals',None):raise error_type('Qualified locals/pointers require a typed frontend')
                current=getattr(current,'type',None)
        for _,child in node.children():visit(child)
    visit(function.body)
