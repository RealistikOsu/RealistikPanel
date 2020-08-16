#Changelog Types
#1 = Normal
#2 = Backend
#3 = Removal
#4 = Add
#5 = Fix
#6 = Replace

#Release types
#1 = Major
#2 = Minor
#3 = Bugix

Changelogs = [
    {
        "Build" : 1585322839,
        "Type" : 1,
        "Summary" : "This update brings changelogs to RealistikPanel! A simple way to view all the new developments!",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added changelogs (as you can see here) to allow admins to view the newest changes!"
            },
            {
                "Type" : 2,
                "Content" : "Added backend permanent data storage system (currently only stores last logon times and last build used)."
            },
            {
                "Type" : 4,
                "Content" : "Added new alert type (info)!"
            }
        ]
    },
    {
        "Build" : 1585326252,
        "Type" : 3,
        "Summary" : "This update fixes some display issues with changelogs.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added new change type (FIX)."
            },
            {
                "Type" : 5,
                "Content" : "Fixed all card headers appearing at the same time."
            },
            {
                "Type" : 4,
                "Content" : "Added margins around changelog types."
            }
        ]
    },
    {
        "Build" : 1585505344,
        "Type" : 2,
        "Summary" : "This build focuses on quality of life changes and minor improvements to the user experiance.",
        "Changes" : [
            {
                "Type" : 2,
                "Content" : "Ordered recent plays by time rather than id."
            },
            {
                "Type" : 6,
                "Image" : "/static/img/changelog/useredit-htmlbadges.png",
                "Content" : "Replaced 'buttons' with badges in users list."
            },
            {
                "Type" : 4,
                "Content" : "Added new changelog type (REPLACE)."
            },
            {
                "Type" : 2,
                "Content" : "Ranking logs now state whether"
            },
            {
                "Type" : 5,
                "Content" : "Replaced GitHub icon in sidebar."
            },
            {
                "Type" : 6,
                "Content" : "Replaced input fields with textareas for multi-line input in user edit."
            },
            {
                "Type" : 5,
                "Content" : "Fixed new lines being broken in user edit."
            },
            {
                "Type" : 4,
                "Content" : "Added image support for changelogs"
            }
        ]
    },
    {
        "Build" : 1585511551,
        "Type" : 2,
        "Summary" : "This update adds a nice dark theme to spare your eyes!",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added dark theme!",
                "Image" : "/static/img/changelog/dark-dash.png"
            },
            {
                "Type" : 4,
                "Content" : "Added theme toggle (between white and dark themes)"
            }
        ]
    },
    {
        "Build" : 1585679639,
        "Type" : 2,
        "Summary" : "This update focuses on adding a list of users thatat one point logged into RealistikPanel.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added admin list (in the RealistikPanel category on the sidebar)"
            },
            {
                "Type" : 5,
                "Content" : "Fixed certain dark mode elements not looking correctly (like coloured card footers)"
            }
        ]
    },
    {
        "Build" : 1585828868,
        "Type" : 3,
        "Summary" : "This update focuses on fixing minor bugs and issues with RealistikPanel, such as accidental bans when privilege group not found",
        "Changes" : [
            {
                "Type" : 5,
                "Content" : "Fixed user privileges that do not have a group to default to Banned, causing the custom privileges to be lost and lead to possible accidental bans."
            },
            {
                "Type" : 3,
                "Content" : "Removed a lot of unnecessary bootstrap JS modules (not used by me), lowering filesize by 40MB."
            },
            {
                "Type" : 5,
                "Content" : "Default config IP lookup is now over HTTPS not to cause JS issues while RealistikPanel is ran over HTTPS."
            }
        ]
    },
    {
        "Build" : 1585936516,
        "Type" : 2,
        "Summary" : "This update's main improvements include the addition of rank all difficulties buttons and fixes to user limitations.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added rank all, love all, and unrank all buttons when ranking a beatmap set alongside a dedicated webhook for the function.",
                "Image" : "/static/img/changelog/rank-collectiveaction.png"
            },
            {
                "Type" : 5,
                "Content" : "Fixed bans and restrictions not removing from leaderboards."
            }
        ]
    },
    {
        "Build" : 1586053016,
        "Type" : 1,
        "Summary" : "This build's objectives are the addition of user search, displaying sidebar options according to privileges and more!",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Sidebar will now only display pages the user has privileges to access."
            },
            {
                "Type" : 4,
                "Content" : "Added user search to the user list, allowing you to search by username or email.",
                "Image" : "/static/img/changelog/user-search.png"
            },
            {
                "Type" : 4,
                "Content" : "User edit actions will only display actions the user has privileges to take."
            },
            {
                "Type" : 4,
                "Content" : "Added release type text to changelogs."
            },
            {
                "Type" : 4,
                "Content" : "Added margin to changelog images to provide a more uniform look."
            },
            {
                "Type" : 5,
                "Content" : "RealistikPanel now will check whether the user is logged in to decide whether to redirect to a 403 or the login page."
            },
            {
                "Type" : 5,
                "Content" : "Fixed online text consistency between rows in the admins list."
            },
            {
                "Type" : 2,
                "Content" : "Threaded user store writes to make dash loading times faster."
            },
            {
                "Type" : 6,
                "Content" : "Set the default panel theme to the dark theme."
            },
            {
                "Type" : 3,
                "Content" : "Removed unintended debugging code from user edit page."
            }
        ]
    },
    {
        "Build" : 1586295323,
        "Type" : 1,
        "Summary" : "This update focuses on improving usability for mobile users and improving the design of RealistikPanel.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added a sidebar toggler for mobile users.",
                "Image" : "/static/img/changelog/base-toggle.jpg"
            },
            {
                "Type" : 4,
                "Content" : "Made user search display the current query."
            },
            {
                "Type": 4,
                "Content" : "Added loading bars to show page loading progress."
            },
            {
                "Type" : 4,
                "Content" : "Differentiated error log exceptions."
            },
            {
                "Type" : 4,
                "Content" : "Made the navigation bar transparent to fit better with the colour scheme of the panel.",
                "Image" : "/static/img/changelog/base-nav.png"
            },
            {
                "Type" : 5,
                "Content" : "Rewrote the navigation bar structure to fix any major layout complications."
            },
            {
                "Type" : 5,
                "Content" : "Fixed unset user pages and admin notes appearing as 'None'."
            },
            {
                "Type" : 2,
                "Content" : "User stores are now cached rather than always being read."
            }
        ]
    },
    {
        "Build": 1586394807,
        "Type" : 3,
        "Summary" : "This build focuses on improving security of RealistikPanel and laying the foundation for future features.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added critical permission check to beatmap ranking."
            },
            {
                "Type" : 2,
                "Content" : "Added supporter management functions (not utilised yet)."
            }
        ]
    },
    {
        "Build" : 1586814976,
        "Type" : 2,
        "Summary" : "This build focuses of adding proper donor management and password changing.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added password changing to user edition."
            },
            {
                "Type" : 4,
                "Content" : "Added supporter giving with set end time."
            },
            {
                "Type" : 2,
                "Content" : "Fixed userpage edition causing issues on servers with the relax gamemode."
            },
            {
                "Type" : 2,
                "Content" : "Un-hardcoded the IPs in /current.json (CurrentIP in config)."
            }
        ]
    },
    {
        "Build" : 1586888761,
        "Type" : 3,
        "Summary" : "This build focuses on fixing exisiting issues with RealistikPanel.",
        "Changes" : [
            {
                "Type" : 5,
                "Content" : "Fixed incorrect column names in delete user."
            },
            {
                "Type" : 5,
                "Content" : "Fixed incorrect redirect after deleting user."
            },
            {
                "Type" : 5,
                "Content" : "Fixed rpusers.json not creating on first start."
            },
            {
                "Type" : 2,
                "Content" : "Online Bancho API call will now return false if there is an error."
            }
        ]
    },
    {
        "Build" : 1587864076,
        "Type" : 2,
        "Summary" : "The aim of this build is to add the viewing of beatmap requests, partial autopilot support and bugfixes to some admin panel functions.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added beatmap requests apge where you can manage all beatmap requests."
            },
            {
                "Type" : 4,
                "Content" : "Added partial support for the autopilot gamemode (eg recent plays)."
            },
            {
                "Type" : 4,
                "Content" : "Added logging to password changes via the panel."
            },
            {
                "Type" : 5,
                "Content" : "Fixed user edition with lacking privileges not returning a valid result."
            },
            {
                "Type" : 5,
                "Content" : "Fixed incorrect column names in user wipe."
            },
            {
                "Type" : 5,
                "Content" : "Fixed generation of safe usernames for users with spaces in their usernames."
            }
        ]
    },
    {
        "Build" : 1588934871,
        "Type" : 2,
        "Summary" : "This update focuses on improving the overall experiance of using RealistikPanel and fixing some bugs.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added pagination to the users page.",
                "Image" : "/static/img/changelog/user-pagination.png"
            },
            {
                "Type" : 4,
                "Content" : "Added pagination to admin logs."
            },
            {
                "Type" : 5,
                "Content" : "Fixed remove from leaderboards not working on autopilot leaderboards."
            },
            {
                "Type" : 5,
                "Content" : "Fixed user wipe causing an SQL syntax error."
            },
            {
                "Type" : 2,
                "Content" : "Disallowed the logging into the bot account."
            }
        ]
    },
    {
        "Build" : 1589636106,
        "Type" : 1,
        "Summary" : "This build's primary objectives are the addition of a clan management system, new privileges and the fix of major bugs.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added clan management, allowing for the viewing, edition and deletion of user clans."
            },
            {
                "Type" : 2,
                "Content" : "Adjusted list splitting."
            },
            {
                "Type" : 2,
                "Content" : "Optimised backend SQL cursor fetches."
            },
            {
                "Type" : 5,
                "Content" : "Fixed specific users causing the whole SQL connection to break."
            }
        ]
    },
    {
        "Build" : 1590359400,
        "Type" : 2,
        "Summary" : "This update focuses on improving the functionality and the quality of life of RealistikPanel.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added an improved ranking UI, featuring a more compact design and Double Time PP calculation.",
                "Image" : "/static/img/changelog/rank-newui.png"
            },
            {
                "Type" : 4,
                "Content" : "Added accuracy to recent plays."
            },
            {
                "Type" : 4,
                "Content" : "Added a global time offset to config that will offset all times in the panel by a specified amount."
            },
            {
                "Type" : 4,
                "Content" : "Added separate wipes for the relax, vanilla and autopilot gamemodes."
            },
            {
                "Type" : 4,
                "Content" : "Added donor remove that will both remove donor privileges, remove custom badge privileges and remove the donor badge."
            },
            {
                "Type" : 4,
                "Content" : "Made donor award automatically give the user the donor badge."
            },
            {
                "Type" : 4,
                "Content" : "Added the ability to kick users from clans via the panel."
            },
            {
                "Type" : 2,
                "Content" : "Used much faster endpoints for server status checks."
            },
            {
                "Type" : 2,
                "Content" : "Decreased likeliness of user edit causing 400 errors."
            },
            {
                "Type" : 2,
                "Content" : "Removed duplicate queries from user deletion."
            }
        ]
    },
    {
        "Build" : 1590437250,
        "Type" : 3,
        "Summary" : "The purpose of this build is to quickly fix a few minor bugs with RealistikPanel.",
        "Changes" : [
            {
                "Type" : 5,
                "Content" : "Fix rank all, love all and unrank all buttons not working (due to recent changes)."
            },
            {
                "Type" : 5,
                "Content" : "Fixed individual rank difficulties not working (due to recent changes)."
            }
        ]
    },
    {
        "Build" : 1591390400,
        "Type" : 1,
        "Summary" : "This update prioritises in improving the statistics shown by the panel.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added a statistics page on the panel that displays daily registrations, recent 500 plays and more."
            },
            {
                "Type" : 4,
                "Content" : "Added rank suggestions to the rank form that fints the top played unranked maps."
            },
            {
                "Type" : 4,
                "Content" : "Added a notice on user edit that shows whether they are currently banned or silenced."
            },
            {
                "Type" : 2,
                "Content" : "Using username_safe for logins again."
            },
            {
                "Type" : 2,
                "Content" : "Deleting a badge now deletes all assignations of the badge."
            }
        ]
    },
    {
        "Build" : 1591494903,
        "Type" : 3,
        "Summary" : "This build fixes a bug with PP calculation on beatmap ranking page and adds more error reporting.",
        "Changes" : [
            {
                "Type" : 2,
                "Content" : "Made PP calc errors show up rather than load infinitely."
            },
            {
                "Type" : 5,
                "Content" : "Fixed the Double Time PP calculation request (before it was requesting with relax)."
            }
        ]
    },
    {
        "Build" : 1591992477,
        "Type" : 2,
        "Summary" : "This release aims at making RealistikPanel a much more complete piece of software.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Added privilege creation (finally) so new groups can now be created from within the panel."
            },
            {
                "Type" : 4,
                "Content" : "Added safety precaution so that if a group with the privileges of 0 (banned) or 3 (regular user) is changed, all users with those privileges will not have them updated."
            },
            {
                "Type" : 4,
                "Content" : "Wipes now will also clear the user's playcount."
            },
            {
                "Type" : 4,
                "Content" : "Added optional webhooks for admin logs and RealistikPanel console logs."
            },
            {
                "Type" : 5,
                "Content" : "Fixed pagination on clans."
            },
            {
                "Type" : 5,
                "Content" : "Fixed registered users being called online users on the stats page."
            },
            {
                "Type" : 5,
                "Content" : "Fixed the redirects on gamemode wipes."
            }
        ]
    },
    {
        "Build" : 1593530430,
        "Type" : 3,
        "Summary" : "This build focuses on fixing minor issues with RealistikPanel.",
        "Changes" : [
            {
                "Type" : 5,
                "Content" : "Some servers being offline no longer causes the dash to not load."
            },
            {
                "Type" : 5,
                "Content" : "Fixed issue with some dark mode elements using  a bright colour scheme"
            },
            {
                "Type" : 5,
                "Content" : "Fix some available beatmap requests showing up as not found."
            },
            {
                "Type" : 5,
                "Content" : "Fix song playback on beatmap rank page."
            }
        ]
    },
    {
        "Build" : 1597593141,
        "Type" : 2,
        "Summary" : "This update bring quality of life improvements, bugfixes and higher server type compatibillity.",
        "Changes" : [
            {
                "Type" : 4,
                "Content" : "Add separate privilege for viewing user IPs."
            },
            {
                "Type" : 4,
                "Content" : "Add logging for freezing users"
            },
            {
                "Type" : 4,
                "Content" : "Added support for Ainu-style freeze timestams."
            },
            {
                "Type" : 6,
                "Content" : "Restricting and freezing now sends a FokaBot message rather than disconnecting the user."
            },
            {
                "Type" : 2,
                "Content" : "Solved rpusers.json not being created correctly."
            },
            {
                "Type" : 2,
                "Content" : "Solve issues with SSL status API."
            }
        ]
    }
]