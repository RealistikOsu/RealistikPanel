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
    }
]