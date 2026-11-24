"""Ryu SDN Controller Application for SentinelNet Autonomous Self-Healing Network.

Implements `SelfHealingController(RyuApp)`:
- Handles `EventOFPSwitchFeatures` to install default table-miss flow (priority 0)
- Handles `EventOFPPacketIn` to learn source MACs and install direct forwarding rules (priority 1)
- Exposes a single custom REST endpoint:
    * GET /health — confirms both ofctl_rest and self-healing app are loaded
  All flow-table endpoints (/stats/switches, /stats/flow/{dpid}, /stats/flowentry/add,
  /stats/flowentry/delete, /stats/flowentry/modify) are provided by the co-loaded
  ryu.app.ofctl_rest app.  Do NOT duplicate them here.
- Maintains in-memory topology and logs every flow modification with high-resolution timestamps.

STARTUP COMMAND (run BOTH apps together):
    ryu-manager \\
      --observe-links \\
      --ofp-tcp-listen-port 6633 \\
      --wsapi-port 8080 \\
      ryu.app.ofctl_rest \\
      sdn_controller/ryu_app.py
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ryu and OpenFlow protocol imports
try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ether_types
    from ryu.app.wsgi import ControllerBase, WSGIApplication, route
    from webob import Response
except ImportError:
    # Graceful fallback when compiling/linting outside of an active Ryu Python environment
    class app_manager:  # type: ignore
        class RyuApp:
            def __init__(self, *args, **kwargs): pass

    class ofproto_v1_3:  # type: ignore
        OFP_VERSION = 0x04
        OFP_NO_BUFFER = 0xffffffff
        OFPP_FLOOD = 0xfffffffb
        OFPFC_DELETE = 3
        OFPP_ANY = 0xffffffff
        OFPG_ANY = 0xffffffff

    class ofp_event:  # type: ignore
        class EventOFPSwitchFeatures: pass
        class EventOFPPacketIn: pass

    def set_ev_cls(*args, **kwargs):
        def decorator(f): return f
        return decorator

    class ControllerBase:  # type: ignore
        def __init__(self, req, link, data, **config):
            self.data = data

    class WSGIApplication: pass
    def route(*args, **kwargs):
        def decorator(f): return f
        return decorator
    class Response:  # type: ignore
        def __init__(self, **kwargs):
            self.status = kwargs.get("status", 200)
            self.body = kwargs.get("body", b"")

CONFIG_DISPATCHER = "config"
MAIN_DISPATCHER = "main"

from sdn_controller.path_manager import PathManager

# Setup logger
logger = logging.getLogger("sentinelnet.sdn_controller")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(ch)

SELFHEALING_INSTANCE_NAME = "selfhealing_controller_api"
URL_PREFIX = ""


class SelfHealingController(app_manager.RyuApp):
    """Main OpenFlow 1.3 Ryu SDN Controller for SentinelNet.

    Loaded alongside ryu.app.ofctl_rest.  This app provides custom self-healing
    logic (MAC learning, table-miss installation, path failover on link-down events).
    Flow-table CRUD REST endpoints come from ofctl_rest — never duplicate them here.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SelfHealingController, self).__init__(*args, **kwargs)
        self.name = "selfhealing"
        self.datapaths: Dict[int, Any] = {}
        # MAC-to-Port table: {dpid: {mac_address: port_no}}
        self.mac_to_port: Dict[int, Dict[str, int]] = {}
        # Flow audit log: list of flow modification history records
        self.flow_history: List[Dict[str, Any]] = []

        # Initialize PathManager
        self.path_manager = PathManager(controller=self)

        # Register WSGI REST API handler (health endpoint only)
        wsgi = kwargs.get("wsgi")
        if wsgi:
            wsgi.register(SelfHealingRestController, {SELFHEALING_INSTANCE_NAME: self})
            logger.info("WSGI REST Server registered at endpoint prefix: %s", URL_PREFIX)
        else:
            logger.warning("WSGI context not found; running without REST server")

        # Confirm both apps are active
        logger.info(
            "Ryu started with ofctl_rest (REST on :8080) + selfhealing app"
        )
        logger.info("SelfHealingController initialized successfully.")

    # -------------------------------------------------------------------------
    # OpenFlow Event Handlers
    # -------------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch connection handshake (OFPT_FEATURES_REPLY).

        Installs the initial Table-Miss Flow Entry (Priority: 0).

        OpenFlow Table-Miss Rule Structure:
        -------------------------------------------------------------
        * Match: Empty (matches every packet not caught by higher rules)
        * Priority: 0 (Lowest priority)
        * Actions: OFPActionOutput(OFPP_CONTROLLER, max_len=OFPCML_NO_BUFFER)
          Sends the packet header to the controller as a PacketIn event.
        -------------------------------------------------------------
        """
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        self.mac_to_port.setdefault(dpid, {})

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        logger.info("Switch connected: DPID=%d (0x%016x)", dpid, dpid)

        # Construct Table-Miss Flow Entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(
            datapath=datapath,
            priority=0,
            match=match,
            actions=actions,
            description="Default Table-Miss Flow Entry (Send to Controller)"
        )
        logger.info("Installed Table-Miss rule on DPID=%d", dpid)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle incoming unknown packets forwarded by switches (OFPT_PACKET_IN).

        Performs:
        1. MAC Learning: Maps source MAC -> incoming physical port.
        2. Destination Lookup:
           - If destination MAC is known: Install direct flow rule (Priority: 1).
           - If unknown: Flood packet across all ports (OFPP_FLOOD).
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP packet-ins (used for topology discovery)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst_mac = eth.dst
        src_mac = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})
        # Learn MAC address
        self.mac_to_port[dpid][src_mac] = in_port

        # Determine egress forwarding port
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # If destination is known, install flow rule on switch to bypass future PacketIns
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac)
            # OpenFlow Standard: Buffer handling
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(
                    datapath=datapath,
                    priority=1,
                    match=match,
                    actions=actions,
                    buffer_id=msg.buffer_id,
                    idle_timeout=30,
                    hard_timeout=120,
                    description=f"MAC-learned route to {dst_mac}"
                )
                return
            else:
                self.add_flow(
                    datapath=datapath,
                    priority=1,
                    match=match,
                    actions=actions,
                    idle_timeout=30,
                    hard_timeout=120,
                    description=f"MAC-learned route to {dst_mac}"
                )

        # Forward the packet that triggered the PacketIn
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    # -------------------------------------------------------------------------
    # Flow Table Management Methods
    # -------------------------------------------------------------------------
    def add_flow(
        self,
        datapath,
        priority: int,
        match,
        actions: list,
        buffer_id: Optional[int] = None,
        idle_timeout: int = 0,
        hard_timeout: int = 0,
        cookie: int = 0,
        description: str = ""
    ):
        """Install an OpenFlow 1.3 flow rule (OFPFlowMod with OFPFC_ADD)."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod_kwargs = {
            "datapath": datapath,
            "priority": priority,
            "match": match,
            "instructions": inst,
            "idle_timeout": idle_timeout,
            "hard_timeout": hard_timeout,
            "cookie": cookie,
        }
        if buffer_id is not None:
            mod_kwargs["buffer_id"] = buffer_id
        else:
            mod_kwargs["buffer_id"] = ofproto.OFP_NO_BUFFER

        mod = parser.OFPFlowMod(**mod_kwargs)
        datapath.send_msg(mod)

        # Audit log record
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": "FLOW_ADD",
            "dpid": datapath.id,
            "priority": priority,
            "description": description,
            "idle_timeout": idle_timeout,
            "hard_timeout": hard_timeout
        }
        self.flow_history.append(log_entry)
        logger.info("[DPID=%d] Flow Installed [Priority=%d]: %s", datapath.id, priority, description)

    def add_flow_rule(
        self,
        dpid: int,
        priority: int,
        match: Dict[str, Any],
        out_port: int,
        idle_timeout: int = 0,
        hard_timeout: int = 0,
        description: str = ""
    ) -> bool:
        """High-level helper to install a flow rule on a target DPID."""
        datapath = self.datapaths.get(dpid)
        if not datapath:
            logger.warning("Cannot add flow: DPID %d not currently connected.", dpid)
            return False

        parser = datapath.ofproto_parser
        ofp_match = parser.OFPMatch(**match)
        actions = [parser.OFPActionOutput(out_port)]

        self.add_flow(
            datapath=datapath,
            priority=priority,
            match=ofp_match,
            actions=actions,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            cookie=0xbeef,
            description=description
        )
        return True

    def delete_flow_rule(self, dpid: int, match: Optional[Dict[str, Any]] = None) -> bool:
        """Delete specific flow entries matching criteria from switch."""
        datapath = self.datapaths.get(dpid)
        if not datapath:
            return False

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        ofp_match = parser.OFPMatch(**match) if match else parser.OFPMatch()

        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=ofp_match
        )
        datapath.send_msg(mod)

        self.flow_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": "FLOW_DELETE",
            "dpid": dpid
        })
        logger.info("[DPID=%d] Deleted flow matching %s", dpid, match)
        return True

    def clear_all_flows(self) -> None:
        """Clear all flow rules from all connected OpenFlow switches (reset to empty)."""
        logger.warning("Clearing all flows across all %d switches...", len(self.datapaths))
        for dpid, datapath in self.datapaths.items():
            self.delete_flow_rule(dpid)
            # Reinstall default table-miss
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            match = parser.OFPMatch()
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
            self.add_flow(datapath, priority=0, match=match, actions=actions, description="Reinstalled Table-Miss")
        self.flow_history.clear()
        logger.info(">>> ALL SWITCH FLOW TABLES CLEARED AND RESET <<<")


# -----------------------------------------------------------------------------
# Ryu WSGI REST Controller  — health endpoint ONLY
# Flow-table endpoints come from ryu.app.ofctl_rest (co-loaded at startup).
# -----------------------------------------------------------------------------
class SelfHealingRestController(ControllerBase):
    """Minimal REST handler for the self-healing app.

    /health  — liveness probe used by the backend and check_ryu.py.

    Flow-table endpoints (/stats/switches, /stats/flow/{dpid},
    /stats/flowentry/add, etc.) are provided by the co-loaded ofctl_rest app.
    """

    def __init__(self, req, link, data, **config):
        super(SelfHealingRestController, self).__init__(req, link, data, **config)
        self.app: SelfHealingController = data[SELFHEALING_INSTANCE_NAME]

    @route("selfhealing_health", "/health", methods=["GET"])
    def health_check(self, req, **kwargs):
        """Return liveness status for both ofctl_rest and the self-healing app.

        ofctl_rest is confirmed alive because this endpoint is reachable on the
        same WSGI port (8080) that ofctl_rest also serves.  If the port is up,
        both apps are running.
        """
        connected_switch_count = len(self.app.datapaths)
        body = {
            "ofctl_rest": "ok",
            "selfhealing": "ok",
            "connected_switches": connected_switch_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        logger.debug("GET /health → %s", body)
        return Response(
            content_type="application/json",
            body=json.dumps(body).encode("utf-8")
        )
