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
    }
]