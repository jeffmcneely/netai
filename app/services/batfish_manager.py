from io import BytesIO
import logging
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


def _serialize_flow(flow_obj: object) -> Dict[str, object]:
    # Batfish Flow objects are attrs-based and not JSON serializable by default.
    return {
        "srcIp": getattr(flow_obj, "srcIp", None),
        "dstIp": getattr(flow_obj, "dstIp", None),
        "srcPort": getattr(flow_obj, "srcPort", None),
        "dstPort": getattr(flow_obj, "dstPort", None),
        "ipProtocol": getattr(flow_obj, "ipProtocol", None),
        "dscp": getattr(flow_obj, "dscp", None),
        "ecn": getattr(flow_obj, "ecn", None),
        "fragmentOffset": getattr(flow_obj, "fragmentOffset", None),
        "packetLength": getattr(flow_obj, "packetLength", None),
        "icmpCode": getattr(flow_obj, "icmpCode", None),
        "icmpVar": getattr(flow_obj, "icmpVar", None),
        "ingressNode": getattr(flow_obj, "ingressNode", None),
        "ingressInterface": getattr(flow_obj, "ingressInterface", None),
        "ingressVrf": getattr(flow_obj, "ingressVrf", None),
        "tcpFlagsAck": getattr(flow_obj, "tcpFlagsAck", None),
        "tcpFlagsCwr": getattr(flow_obj, "tcpFlagsCwr", None),
        "tcpFlagsEce": getattr(flow_obj, "tcpFlagsEce", None),
        "tcpFlagsFin": getattr(flow_obj, "tcpFlagsFin", None),
        "tcpFlagsPsh": getattr(flow_obj, "tcpFlagsPsh", None),
        "tcpFlagsRst": getattr(flow_obj, "tcpFlagsRst", None),
        "tcpFlagsSyn": getattr(flow_obj, "tcpFlagsSyn", None),
        "tcpFlagsUrg": getattr(flow_obj, "tcpFlagsUrg", None),
    }


def _is_flow_like(value: object) -> bool:
    return all(
        hasattr(value, attr)
        for attr in ("srcIp", "dstIp", "ipProtocol", "packetLength", "fragmentOffset")
    )


def _serialize_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if value.__class__.__name__ == "Flow" or _is_flow_like(value):
        return _serialize_flow(value)

    if isinstance(value, list):
        return [_serialize_value(item) for item in value]

    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}

    if hasattr(value, "__dict__") and value.__dict__:
        return {
            key: _serialize_value(item)
            for key, item in value.__dict__.items()
            if not key.startswith("_")
        }

    return str(value)


def _frame_to_records(frame) -> List[Dict[str, object]]:
    records = frame.fillna("").to_dict(orient="records")
    serialized: List[Dict[str, object]] = []
    for row in records:
        serialized.append({key: _serialize_value(value) for key, value in row.items()})
    return serialized


class BatfishManager:
    def __init__(self, server: str):
        self.server = server
        self._bf = None

    def _session(self):
        if self._bf is not None:
            return self._bf

        try:
            from pybatfish.client.session import Session
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pybatfish is not installed") from exc

        logger.debug("Initializing Batfish session host=%s", self.server)
        self._bf = Session(host=self.server)
        return self._bf

    def init_snapshot(self, zip_data: bytes, config_folder: str) -> str:
        bf = self._session()
        snapshot_name = config_folder
        print(
            f"[BATFISH DEBUG] init_snapshot host={self.server} snapshot={snapshot_name} zip_bytes={len(zip_data)} overwrite=True",
            flush=True,
        )
        logger.debug(
            "Sending Batfish init_snapshot request host=%s snapshot=%s zip_bytes=%d overwrite=%s",
            self.server,
            snapshot_name,
            len(zip_data),
            True,
        )
        bf.init_snapshot(BytesIO(zip_data), name=snapshot_name, overwrite=True)
        return snapshot_name

    def run_filter_line_reachability(self) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=filterLineReachability host={self.server}",
            flush=True,
        )
        query = bf.q.filterLineReachability()
        logger.debug("Sending Batfish query host=%s query=%s", self.server, "filterLineReachability")
        frame = query.answer().frame()
        return _frame_to_records(frame)

    def run_search_filters(self, header_constraints: object) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=searchFilters host={self.server} headers={header_constraints!r}",
            flush=True,
        )
        query = bf.q.searchFilters(headers=header_constraints)
        logger.debug(
            "Sending Batfish query host=%s query=%s headers=%r",
            self.server,
            "searchFilters",
            header_constraints,
        )
        frame = query.answer().frame()
        return _frame_to_records(frame)

    def run_search_filters_for_acl(self, node_hostname: str, filter_name: str) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=searchFilters host={self.server} nodes={node_hostname!r} filters={filter_name!r}",
            flush=True,
        )
        query = bf.q.searchFilters(nodes=node_hostname, filters=filter_name)
        logger.debug(
            "Sending Batfish query host=%s query=%s node=%s filter=%s",
            self.server,
            "searchFilters",
            node_hostname,
            filter_name,
        )
        frame = query.answer().frame()
        return _frame_to_records(frame)

    def run_interface_properties(self, node_hostname: Optional[str] = None) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=interfaceProperties host={self.server} nodes={node_hostname if node_hostname else '*'}",
            flush=True,
        )
        query = (
            bf.q.interfaceProperties(nodes=node_hostname)
            if node_hostname
            else bf.q.interfaceProperties()
        )
        logger.debug(
            "Sending Batfish query host=%s query=%s node=%s",
            self.server,
            "interfaceProperties",
            node_hostname or "*",
        )
        frame = query.answer().frame()
        return _frame_to_records(frame)

    def run_node_properties(
        self,
        nodes: Optional[object] = None,
        properties: Optional[object] = None,
    ) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=nodeProperties host={self.server} nodes={nodes if nodes else '*'} properties={properties if properties else '*'}",
            flush=True,
        )
        kwargs: Dict[str, object] = {}
        if nodes is not None:
            kwargs["nodes"] = nodes
        if properties is not None:
            kwargs["properties"] = properties

        query = bf.q.nodeProperties(**kwargs)
        logger.debug(
            "Sending Batfish query host=%s query=%s nodes=%r properties=%r",
            self.server,
            "nodeProperties",
            nodes,
            properties,
        )
        frame = query.answer().frame()
        return _frame_to_records(frame)

    def run_named_structures(
        self,
        nodes: Optional[object] = None,
        structure_types: Optional[object] = None,
        structure_names: Optional[object] = None,
    ) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=namedStructures host={self.server} nodes={nodes if nodes else '*'} structure_types={structure_types if structure_types else '*'}",
            flush=True,
        )
        kwargs: Dict[str, object] = {}
        if nodes is not None:
            kwargs["nodes"] = nodes
        if structure_types is not None:
            kwargs["structureTypes"] = structure_types
        if structure_names is not None:
            kwargs["structureNames"] = structure_names

        query = bf.q.namedStructures(**kwargs)
        logger.debug(
            "Sending Batfish query host=%s query=%s nodes=%r structure_types=%r structure_names=%r",
            self.server,
            "namedStructures",
            nodes,
            structure_types,
            structure_names,
        )
        frame = query.answer().frame()
        return _frame_to_records(frame)

    def run_switched_vlan_properties(self, node_hostname: Optional[str] = None) -> List[Dict[str, object]]:
        bf = self._session()
        print(
            f"[BATFISH DEBUG] query=switchedVlanProperties host={self.server} nodes={node_hostname if node_hostname else '*'}",
            flush=True,
        )
        query = (
            bf.q.switchedVlanProperties(nodes=node_hostname)
            if node_hostname
            else bf.q.switchedVlanProperties()
        )
        logger.debug(
            "Sending Batfish query host=%s query=%s node=%s",
            self.server,
            "switchedVlanProperties",
            node_hostname or "*",
        )
        frame = query.answer().frame()
        return _frame_to_records(frame)


def build_header_constraints(filters: Dict[str, object]) -> Optional[object]:
    if not filters:
        return None

    try:
        from pybatfish.datamodel.flow import HeaderConstraints
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pybatfish HeaderConstraints import failed") from exc

    kwargs: Dict[str, object] = {}
    force_string_fields = {"srcIps", "dstIps", "fragmentOffsets", "packetLengths"}

    mapping = {
        "srcIps": "srcIps",
        "dstIps": "dstIps",
        "srcPorts": "srcPorts",
        "dstPorts": "dstPorts",
        "applications": "applications",
        "ipProtocols": "ipProtocols",
        "icmpCodes": "icmpCodes",
        "icmpTypes": "icmpTypes",
        "dscps": "dscps",
        "ecns": "ecns",
        "packetLengths": "packetLengths",
        "fragmentOffsets": "fragmentOffsets",
        "tcpFlags": "tcpFlags",
    }

    for ui_key, hc_key in mapping.items():
        value = filters.get(ui_key)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        if hc_key in force_string_fields:
            if isinstance(value, list):
                value = ",".join(str(item) for item in value)
            else:
                value = str(value)
        kwargs[hc_key] = value

    if not kwargs:
        return None

    return HeaderConstraints(**kwargs)
