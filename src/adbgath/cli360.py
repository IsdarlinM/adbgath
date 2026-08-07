from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise RuntimeError("CLI subcommand registry was not found")


def _service(module: Any, args: argparse.Namespace):
    from .adb import AdbClient
    from .service import AdbgathService

    adb = AdbClient(args.adb_path) if getattr(args, "adb_path", None) else None
    return AdbgathService(adb, workspace=getattr(args, "workspace", None))


def patch_cli(module: Any) -> None:
    if getattr(module, "_adbgath_360_patched", False):
        return
    original_build = module.build_parser
    original_run = module.run

    def build_parser():
        parser = original_build()
        commands = _subcommands(parser)
        root_sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))

        if "artifact-store" not in commands:
            p = root_sub.add_parser("artifact-store", help="Manage deduplicated content-addressed evidence objects.")
            p.add_argument("mode", nargs="?", choices=["status","import","list","verify","materialize","migrate","gc"], default="status")
            p.add_argument("--path"); p.add_argument("--digest"); p.add_argument("--output"); p.add_argument("--project-id")
            p.add_argument("--no-compress", action="store_true"); p.add_argument("--apply", action="store_true", help="Apply migration/GC instead of dry run.")

        if "correlate" not in commands:
            p = root_sub.add_parser("correlate", help="Correlate static and runtime application evidence.")
            p.add_argument("package"); p.add_argument("--apk")

        if "policy" not in commands:
            p = root_sub.add_parser("policy", help="Inspect and manage RBAC policy.")
            p.add_argument("mode", nargs="?", choices=["show","check","set","delete"], default="show")
            p.add_argument("--role", choices=["viewer","analyst","operator","administrator"], default="viewer")
            p.add_argument("--action", default=""); p.add_argument("--effect", choices=["allow","deny"], default="allow"); p.add_argument("--approved", action="store_true")

        if "audit" not in commands:
            p = root_sub.add_parser("audit", help="Inspect or verify the append-only audit chain.")
            p.add_argument("mode", nargs="?", choices=["list","verify"], default="list"); p.add_argument("--limit", type=int, default=200)

        if "sbom" not in commands:
            p = root_sub.add_parser("sbom", help="Generate CycloneDX or SPDX runtime SBOM.")
            p.add_argument("--format", choices=["cyclonedx","spdx"], default="cyclonedx"); p.add_argument("--output", required=True)
        if "governance" not in commands:
            p = root_sub.add_parser("governance", help="Legal holds and AES-256-GCM evidence vault operations.")
            p.add_argument("mode", nargs="?", choices=["holds","hold","release","seal","unseal"], default="holds")
            p.add_argument("--project-id"); p.add_argument("--reason"); p.add_argument("--actor", default="local-operator"); p.add_argument("--path"); p.add_argument("--output"); p.add_argument("--passphrase-env", default="ADBGATH_VAULT_PASSPHRASE")


        plugin = commands.get("plugin")
        if plugin:
            sub = next((a for a in plugin._actions if isinstance(a, argparse._SubParsersAction)), None)
            if sub and "keygen" not in sub.choices:
                k = sub.add_parser("keygen", help="Generate Ed25519 plugin signing keys."); k.add_argument("--private-key", required=True); k.add_argument("--public-key", required=True)
                s = sub.add_parser("sign", help="Sign a plugin manifest and file."); s.add_argument("--manifest", required=True); s.add_argument("--plugin-file", required=True); s.add_argument("--private-key", required=True); s.add_argument("--output", required=True)
                v = sub.add_parser("verify", help="Verify an Ed25519 signed plugin bundle."); v.add_argument("--bundle", required=True); v.add_argument("--plugin-file", required=True); v.add_argument("--public-key", required=True)
                pl = sub.add_parser("publisher-list", help="List trusted plugin publishers.")
                pa = sub.add_parser("publisher-add", help="Trust an Ed25519 publisher key."); pa.add_argument("name"); pa.add_argument("--public-key", required=True)
                pr = sub.add_parser("publisher-revoke", help="Revoke a trusted plugin publisher."); pr.add_argument("name")
                tv = sub.add_parser("verify-trusted", help="Verify a plugin against a trusted non-revoked publisher."); tv.add_argument("--bundle", required=True); tv.add_argument("--plugin-file", required=True); tv.add_argument("--publisher", required=True)

        if "lab" not in commands:
            lab = root_sub.add_parser("lab", help="Secure distributed Android lab controller and outbound agents.")
            sub = lab.add_subparsers(dest="lab_mode", required=True)
            sub.add_parser("status"); sub.add_parser("agents"); sub.add_parser("pools")
            pki = sub.add_parser("pki-init"); pki.add_argument("--dir", required=True)
            cc = sub.add_parser("controller-cert"); cc.add_argument("--dir", required=True); cc.add_argument("--name", default="adbgath-controller"); cc.add_argument("--host", action="append", default=[])
            enroll = sub.add_parser("agent-enroll"); enroll.add_argument("name"); enroll.add_argument("--pki-dir", required=True); enroll.add_argument("--controller", required=True)
            pool = sub.add_parser("pool-create"); pool.add_argument("name")
            pa = sub.add_parser("pool-add"); pa.add_argument("pool"); pa.add_argument("agent"); pa.add_argument("device")
            jobs = sub.add_parser("jobs"); jobs.add_argument("--limit", type=int, default=200)
            js = sub.add_parser("job-submit"); js.add_argument("--agent", required=True); js.add_argument("--action", required=True); js.add_argument("--payload", default="{}"); js.add_argument("--role", choices=["viewer","analyst","operator","administrator"], default="operator"); js.add_argument("--actor", default="local-operator"); js.add_argument("--approved", action="store_true")
            ps = sub.add_parser("pool-submit"); ps.add_argument("--pool", required=True); ps.add_argument("--action", required=True); ps.add_argument("--payload", default="{}"); ps.add_argument("--role", choices=["viewer","analyst","operator","administrator"], default="operator"); ps.add_argument("--actor", default="local-operator"); ps.add_argument("--approved", action="store_true")
            jc = sub.add_parser("job-cancel"); jc.add_argument("job_id")
            ctl = sub.add_parser("controller"); ctl.add_argument("--host", default="127.0.0.1"); ctl.add_argument("--port", type=int, default=9443); ctl.add_argument("--cert", required=True); ctl.add_argument("--key", required=True); ctl.add_argument("--ca", required=True)
            ar = sub.add_parser("agent-run"); ar.add_argument("--config", required=True); ar.add_argument("--interval", type=int, default=5); ar.add_argument("--once", action="store_true")
        return parser

    def run(args):
        if args.command == "artifact-store":
            return _service(module,args).artifact_store(args.mode,path=args.path,digest=args.digest,output=args.output,project_id=args.project_id,compress=not args.no_compress,dry_run=not args.apply)
        if args.command == "correlate": return _service(module,args).correlate(args.device,args.package,apk=args.apk)
        if args.command == "policy": return _service(module,args).policy_operation(args.mode,role=args.role,action=args.action,effect=args.effect,approved=args.approved)
        if args.command == "audit": return _service(module,args).audit_operation(args.mode,limit=args.limit)
        if args.command == "sbom": return _service(module,args).sbom_generate(args.format,args.output)
        if args.command == "governance":
            import os, getpass
            passphrase=""
            if args.mode in {"seal","unseal"}:
                passphrase=os.environ.get(args.passphrase_env, "") or getpass.getpass("Vault passphrase: ")
            return _service(module,args).governance(args.mode,project_id=args.project_id,reason=args.reason,actor=args.actor,path=args.path,output=args.output,passphrase=passphrase)
        if args.command == "plugin" and getattr(args,"plugin_mode",None) in {"keygen","sign","verify","publisher-list","publisher-add","publisher-revoke","verify-trusted"}:
            service=_service(module,args)
            if args.plugin_mode=="keygen": return service.plugin_keygen(args.private_key,args.public_key)
            if args.plugin_mode=="sign": return service.plugin_sign(args.manifest,args.plugin_file,args.private_key,args.output)
            if args.plugin_mode=="verify": return service.plugin_verify_signed(args.bundle,args.plugin_file,args.public_key)
            if args.plugin_mode=="publisher-list": return service.plugin_publisher("list")
            if args.plugin_mode=="publisher-add": return service.plugin_publisher("add",name=args.name,public_key=args.public_key)
            if args.plugin_mode=="publisher-revoke": return service.plugin_publisher("revoke",name=args.name)
            return service.plugin_verify_trusted(args.bundle,args.plugin_file,args.publisher)
        if args.command == "lab":
            service=_service(module,args); mode=args.lab_mode
            if mode=="status": return service.lab_status()
            if mode=="agents": return service.store.list_lab_agents()
            if mode=="pools": return service.store.list_lab_pools()
            if mode=="pki-init": return service.lab_pki_init(args.dir)
            if mode=="controller-cert": return service.lab_controller_certificate(args.dir,name=args.name,hosts=args.host)
            if mode=="agent-enroll": return service.lab_agent_enroll(args.name,pki_dir=args.pki_dir,controller=args.controller)
            if mode=="pool-create": return service.lab_pool_manage("create",name=args.name)
            if mode=="pool-add": return service.lab_pool_manage("add",pool=args.pool,agent=args.agent,device=args.device)
            if mode=="jobs": return service.store.list_lab_jobs(args.limit)
            if mode=="job-submit": return service.lab_job_submit(agent=args.agent,action=args.action,payload=json.loads(args.payload),role=args.role,actor=args.actor,approved=args.approved)
            if mode=="pool-submit": return service.lab_pool_submit(pool=args.pool,action=args.action,payload=json.loads(args.payload),role=args.role,actor=args.actor,approved=args.approved)
            if mode=="job-cancel": return service.store.cancel_lab_job(args.job_id)
            if mode=="controller":
                from .lab.controller import serve_controller
                serve_controller(service,host=args.host,port=args.port,cert=args.cert,key=args.key,ca=args.ca); return {"stopped":True}
            if mode=="agent-run":
                from .lab.agent import LabAgent
                cfg=json.loads(Path(args.config).read_text(encoding="utf-8"))
                agent=LabAgent(service,agent_id=cfg["agent_id"],token=cfg["token"],controller=cfg["controller"],cert=cfg["cert"],key=cfg["key"],ca=cfg["ca"])
                if args.once: return agent.cycle()
                agent.run(interval=args.interval); return {"stopped":True}
        return original_run(args)

    module.build_parser=build_parser; module.run=run; module._adbgath_360_patched=True
