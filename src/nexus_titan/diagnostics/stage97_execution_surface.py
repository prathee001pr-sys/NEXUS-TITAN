"""Read-only static inventory of Stage97 Crypto paper mutation call surfaces.

This is an intentionally conservative audit, NOT a permission system. Python
reflection/import patterns can evade static analysis; therefore the final release
classification is always NO-GO until a separately authenticated runtime gateway
is installed and independently verified at all entrypoints.
"""
from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any


# Pinned exact pre-audit GitHub PR #140 source identities; not provenance proof.
STAGE97_BASELINE_GIT_BLOB = "0c1600848c8095e05581531e4e04f3acc7265bd7"
REVIEWED_GATEWAY_BASELINE_GIT_BLOB = "43fc5a77e0ca908ba409116634519fbe4046acb3"


@dataclass(frozen=True, slots=True)
class Stage97ApplySurface:
    file: str
    scope: str
    line: int
    call: str
    disposition: str


def _blob_sha(data: bytes) -> str:
        return sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _calls_in_functions(tree: ast.AST, rel: str) -> tuple[Stage97ApplySurface, ...]:
    """Discover explicit .apply() calls in Crypto-adjacent source modules.

    This is deliberately an inventory only, not proof of all runtime aliases.
    New callsites are conservatively classified as UNKNOWN_REQUIRES_REVIEW.
    """
    out: list[Stage97ApplySurface] = []
    scopes = [tree] + [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in scopes:
        # Include top-level module calls and each distinct function scope.
        # Do not attribute nested callbacks to the containing function.
        direct = []
        def visit(node: ast.AST) -> None:
            if node is not current and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                return
            if isinstance(node, ast.Call):
                direct.append(node)
            for child in ast.iter_child_nodes(node):
                visit(child)
        current=node
        visit(node)
        for call in direct:
            # A directly retrieved bound method may be used later through a
            # runtime alias. Conservatively flag explicit getattr(...,'apply')
            # instead of giving it a clean static inventory.
            dynamic_lookup = (isinstance(call.func, ast.Name)
                and call.func.id == "getattr" and len(call.args) >= 2
                and isinstance(call.args[1], ast.Constant)
                and call.args[1].value == "apply")
            if dynamic_lookup:
                expression = ast.unparse(call)
            elif isinstance(call.func, ast.Attribute) and call.func.attr == "apply":
                expression = ast.unparse(call.func)
            else:
                continue
            disposition = (
                "KNOWN_OPT_IN_REVIEWED_WRAPPER" if
                not dynamic_lookup and
                rel == "src/nexus_titan/operations/crypto_spot_reviewed_paper.py"
                and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "submit_reviewed_synthetic_paper"
                and expression == "book.apply" else
                "UNKNOWN_REQUIRES_REVIEW"
            )
            result = Stage97ApplySurface(rel, getattr(node, "name", "<module>"), call.lineno, expression, disposition)
            if result not in out:out.append(result)
    return tuple(sorted(out,key=lambda s:(s.file,s.line,s.scope)))


def audit_stage97_paper_execution(root: str | Path) -> dict[str, Any]:
    """Return a diagnostic that can NEVER grant a permit or production signoff."""
    root=Path(root).resolve()
    src=root/"src/nexus_titan"
    stage=src/"operations/stage97_crypto_paper.py"
    gateway=src/"operations/crypto_spot_reviewed_paper.py"
    state={"stage97_sha":None,"gateway_sha":None,"pinned_source_match":False,
           "source_parse_ok":False,"public_stage97_apply":False,
           "opt_in_review_before_apply":False,"unknown_crypto_apply_calls":[],
           "explicit_crypto_apply_calls":[],"inventory_scope":"static_source_only",
           "runtime_reflection_or_external_imports_ruled_out":False,
           "mandatory_all_path_independent_risk_verified":False,
           "authenticated_human_authority_verified":False,
           "live_trading_authorized":False,"main_merge_authorized":False,
           "production_ready":False,"verdict":"BLOCKED_UNVERIFIED_SOURCE"}
    if not src.is_dir() or not stage.is_file() or not gateway.is_file():return state
    if stage.is_symlink() or gateway.is_symlink():return state
    stage_bytes=stage.read_bytes(); gateway_bytes=gateway.read_bytes()
    state["stage97_sha"]=_blob_sha(stage_bytes)
    state["gateway_sha"]=_blob_sha(gateway_bytes)
    state["pinned_source_match"]=(state["stage97_sha"]==STAGE97_BASELINE_GIT_BLOB
        and state["gateway_sha"]==REVIEWED_GATEWAY_BASELINE_GIT_BLOB)
    try:
        stage_tree=ast.parse(stage_bytes,filename=str(stage))
        gateway_tree=ast.parse(gateway_bytes,filename=str(gateway))
        sources={}
        for file in src.rglob("*.py"):
            if file.is_symlink() or not file.resolve().is_relative_to(src.resolve()):
                raise ValueError("Symlink or external source encountered")
            # Only scan sources that import/mention CryptoPaperBook or the Stage97
            # module. Generic F&O ".apply" routes are unrelated.
            content=file.read_text(encoding="utf-8")
            if ("CryptoPaperBook" not in content and
                    "stage97_crypto_paper" not in content and
                    "crypto_spot_reviewed_paper" not in content):
                continue
            rel=file.relative_to(root).as_posix()
            sources[rel]=ast.parse(content,filename=str(file))
        state["source_parse_ok"]=True
    except (OSError,ValueError,SyntaxError,UnicodeError):return state
    for node in stage_tree.body:
        if isinstance(node,ast.ClassDef) and node.name=="CryptoPaperBook":
            state["public_stage97_apply"]=any(isinstance(m,ast.FunctionDef) and m.name=="apply" for m in node.body)
            break
    funcs={n.name:n for n in gateway_tree.body if isinstance(n,ast.FunctionDef)}
    func=funcs.get("submit_reviewed_synthetic_paper")
    if func:
        calls=[n for n in ast.walk(func) if isinstance(n,ast.Call)]
        reviews=[n.lineno for n in calls if isinstance(n.func,ast.Name) and n.func.id=="review_synthetic_crypto_spot_risk"]
        applies=[n.lineno for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=="apply" and isinstance(n.func.value,ast.Name) and n.func.value.id=="book"]
        # Lexical order is useful evidence but NOT a proof of control-flow dominance.
        state["opt_in_review_before_apply"]=len(reviews)==1 and len(applies)==1 and reviews[0]<applies[0]
    surfaces=[]
    for rel, tree in sources.items():
        surfaces.extend(_calls_in_functions(tree,rel))
    surfaces.sort(key=lambda x:(x.file,x.line,x.scope))
    state["explicit_crypto_apply_calls"]=[asdict(s) for s in surfaces]
    state["unknown_crypto_apply_calls"]=[asdict(s) for s in surfaces if s.disposition!="KNOWN_OPT_IN_REVIEWED_WRAPPER"]
    # Structural diagnostics may pass while mandatory all-path enforcement is
    # still categorically unproven: public Stage97.apply remains importable.
    if not state["pinned_source_match"] or not state["source_parse_ok"]:
        state["verdict"]="BLOCKED_SOURCE_DRIFT"
    elif not state["public_stage97_apply"] or not state["opt_in_review_before_apply"]:
        state["verdict"]="BLOCKED_REVIEW_GATE_STRUCTURE"
    elif state["unknown_crypto_apply_calls"]:
        state["verdict"]="BLOCKED_NEW_POTENTIAL_EXECUTION_PATHS"
    else:
        state["verdict"]="BLOCKED_PUBLIC_DIRECT_STAGE97_APPLY"
    return state
