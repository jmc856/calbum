"""gspread-backed implementation of calbum.sheets.SheetBackend. The only
place gspread itself gets imported — see PLAN.md "The module boundary that
matters", the same isolation pattern as spotify/ and discogs/.

replace_tab issues 3 HTTP round-trips per tab (delete+create, write values,
format+freeze+protect), plus one `worksheets()` call shared across the whole
instance — down from 9 independent calls per tab. Each Sheets API call is
quota'd (60 reads + 60 writes/minute/user), so collapsing this matters for a
run that touches several tabs.
"""

from __future__ import annotations

import base64
import json
import os

import gspread
from gspread.utils import ValueInputOption, a1_range_to_grid_range, rowcol_to_a1


def load_sa_json() -> str:
    """GOOGLE_SA_JSON_B64 is the service-account key JSON, base64-encoded —
    not stored as raw JSON. The key's private_key field embeds literal `\\n`
    sequences, and both python-dotenv (loading .env locally) and shells
    unescape those into real newlines depending on quoting, which corrupts
    the JSON (a raw newline inside a JSON string is invalid). Base64 has no
    quotes, backslashes, or newlines to mis-parse, so it survives any
    .env/shell/GitHub-Actions-secret round trip intact."""
    encoded = os.environ["GOOGLE_SA_JSON_B64"]
    return base64.b64decode(encoded).decode("utf-8")


class GspreadSheetBackend:
    def __init__(self, sa_json: str, sheet_id: str):
        credentials = json.loads(sa_json)
        client = gspread.service_account_from_dict(credentials)
        self._spreadsheet = client.open_by_key(sheet_id)
        self._service_account_email = credentials["client_email"]
        # Snapshot of the tabs that exist at construction time — this is all
        # replace_tab needs to know (whether a same-titled tab needs
        # deleting first), and fetching it once here means every replace_tab
        # call skips its own worksheet(title) metadata lookup.
        self._existing_sheet_ids = {ws.title: ws.id for ws in self._spreadsheet.worksheets()}

    @classmethod
    def from_env(cls) -> GspreadSheetBackend:
        """Credential acquisition end to end, so sheets.py (which otherwise
        knows nothing past Album and list[list[object]]) doesn't have to."""
        return cls(sa_json=load_sa_json(), sheet_id=os.environ["SHEET_ID"])

    def replace_tab(self, title: str, rows: list[list[object]]) -> None:
        """Delete-if-present, create fresh, write, freeze header, protect.
        Deleting and recreating (rather than clearing in place) is what
        makes "delete a tab by hand, next run rebuilds it" — the stage's own
        done-when — true for free, and sidesteps ever needing to edit
        through a protection left over from a prior run: that protection is
        deleted along with the old tab before the new one is protected."""
        num_rows = max(len(rows), 1)
        num_cols = max((len(row) for row in rows), default=1)

        create_requests: list[dict] = []
        existing_id = self._existing_sheet_ids.get(title)
        if existing_id is not None:
            create_requests.append({"deleteSheet": {"sheetId": existing_id}})
        create_requests.append(
            {
                "addSheet": {
                    "properties": {
                        "title": title,
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": num_rows, "columnCount": num_cols},
                    }
                }
            }
        )
        create_response = self._spreadsheet.batch_update({"requests": create_requests})
        sheet_id = create_response["replies"][-1]["addSheet"]["properties"]["sheetId"]
        self._existing_sheet_ids[title] = sheet_id

        if rows:
            # USER_ENTERED, not RAW: RAW would write "=HYPERLINK(...)" as a
            # literal string instead of parsing it as a formula.
            self._spreadsheet.values_update(
                f"{title}!A1",
                params={"valueInputOption": ValueInputOption.user_entered},
                body={"values": rows},
            )

        # Formatting before protection, deliberately, in one request array:
        # addProtectedRange restricts further edits to whatever
        # account/permission mechanism is set up for that range (the "can't
        # remove yourself as an editor" class of bug fixed earlier this
        # session), so any formatting must land first — doing it after risks
        # rediscovering that same class of failure from the other side.
        # batchUpdate applies its requests array in order, so that ordering
        # is preserved here exactly as it was across separate calls.
        #
        # The header format is its own full textFormat object, not a
        # bold-only follow-up — confirmed live that the Sheets API replaces
        # a cell's entire textFormat per repeatCell request rather than
        # merging fields, so a bold-only request after the base font request
        # wiped out fontFamily/fontSize on the header row.
        last_cell = rowcol_to_a1(num_rows, num_cols)
        full_range = a1_range_to_grid_range(f"A1:{last_cell}", sheet_id)
        header_range = a1_range_to_grid_range(f"A1:{rowcol_to_a1(1, num_cols)}", sheet_id)
        base_font = {"fontFamily": "Roboto", "fontSize": 10}

        finalize_requests = [
            {
                "repeatCell": {
                    "range": full_range,
                    "cell": {"userEnteredFormat": {"textFormat": base_font}},
                    "fields": "userEnteredFormat(textFormat)",
                }
            },
            {
                "repeatCell": {
                    "range": header_range,
                    "cell": {"userEnteredFormat": {"textFormat": {**base_font, "bold": True}}},
                    "fields": "userEnteredFormat(textFormat)",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": num_cols}
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties/frozenRowCount",
                }
            },
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": full_range,
                        "description": "Generated by calbum — hand edits are overwritten every run.",
                        "warningOnly": False,
                        "requestingUserCanEdit": True,
                        # gspread's own docstring: "editor_users_emails must
                        # at least contain the e-mail address used to open
                        # that SpreadSheet." Confirmed live: omitting this
                        # (even with requestingUserCanEdit alone) fails with
                        # "You can't remove yourself as an editor" — an
                        # empty editors list is sent as an explicit "no
                        # editors", not "auto-add owner" as the docstring's
                        # first paragraph implies.
                        "editors": {"users": [self._service_account_email], "groups": []},
                    }
                }
            },
        ]
        self._spreadsheet.batch_update({"requests": finalize_requests})
