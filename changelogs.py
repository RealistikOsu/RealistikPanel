#Changelog Types
#1 = Normal
#2 = Backend
#3 = Removal
#4 = Add
#5 = Fix

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
    }
]